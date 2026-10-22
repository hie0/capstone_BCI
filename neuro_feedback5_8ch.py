from __future__ import annotations

import argparse
import csv
import hashlib
import math
import random
import threading
import time
from bisect import bisect_right
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from scipy.signal import sosfilt
from sklearn.metrics import balanced_accuracy_score, f1_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from psychopy import core, event, visual
from explorepy import Explore
from explorepy.stream_processor import TOPICS


# =============================================================================
# Experiment markers
# =============================================================================
SESSION_START = 1
CALIBRATION_START = 10
CALIBRATION_REST_ONSET = 11
CALIBRATION_LEFT_ONSET = 12
CALIBRATION_RIGHT_ONSET = 13
CALIBRATION_END = 14
CALIBRATION_BLOCK_REST_ONSET = 15
MAIN_EXPERIMENT_START = 16
INITIAL_RELAX_ONSET = 20
MAIN_RELAX_ONSET = 21
TRIAL_REST_ONSET = 30
PRED_LEFT_ONSET = 31
PRED_RIGHT_ONSET = 32
CLASSIFICATION_ONSET = 33
BLOCK_REST_ONSET = 34
LEVEL_0_ONSET = 40
LEVEL_1_ONSET = 41
LEVEL_2_ONSET = 42
LEVEL_3_ONSET = 43
SUCCESS_LEFT_ONSET = 51
SUCCESS_RIGHT_ONSET = 52
FAIL_LEFT_ONSET = 61
FAIL_RIGHT_ONSET = 62
# Protocol4-style offline collection, reserved non-overlapping marker namespace.
OFFLINE_START = 70
OFFLINE_RELAX_ONSET = 71
OFFLINE_FIXATION_ONSET = 72
OFFLINE_CUE_LEFT_ONSET = 73
OFFLINE_CUE_RIGHT_ONSET = 74
OFFLINE_MI_LEFT_ONSET = 75
OFFLINE_MI_RIGHT_ONSET = 76
OFFLINE_REST_ONSET = 77
OFFLINE_END = 78
CALIBRATION_RETRY_START = 79
CALIBRATION_RETRY_END = 80
SESSION_END = 99
EXPERIMENT_ABORTED = 98


# =============================================================================
# Experiment design
# =============================================================================
N_TRIALS = 30
CALIBRATION_TRIALS = 20
CALIBRATION_BLOCK_SIZE = 10
CALIBRATION_MI_DURATION = 3.0
CALIBRATION_REST_DURATION = 1.0
CALIBRATION_BLOCK_REST_DURATION = 5.0

CLASSIFICATION_WINDOW = 0.5
CALIBRATION_WINDOWS_PER_TRIAL = int(round(CALIBRATION_MI_DURATION / CLASSIFICATION_WINDOW))  # 6
CALIBRATION_OOF_FOLDS = 5

OFFLINE_TRAIN_WEIGHT = 0.80
DAILY_TRAIN_WEIGHT = 0.20
NEW_THRESHOLD = 0.50
GATE_MIN_AUC = 0.60
GATE_MIN_DELTA_P = 0.03
GATE_MIN_LEFT_RECALL = 0.50
GATE_MIN_RIGHT_RECALL = 0.50
MAX_CALIBRATION_ATTEMPTS = 2
OFFLINE_FIXATION_DURATION = 2.0
OFFLINE_CUE_DURATION = 0.7
OFFLINE_MI_DURATION = 3.0
OFFLINE_REST_DURATION = 2.0
OFFLINE_RELAX_DURATION = 5.0

INITIAL_RELAX_DURATION = 5.0
MAIN_RELAX_DURATION = 5.0
TRIAL_REST_DURATION = 1.0
BLOCK_REST_INTERVAL = 10
BLOCK_REST_DURATION = 5.0
MAX_CLASSIFICATION_DURATION = 15.0
MAX_PREDICTIONS = int(MAX_CLASSIFICATION_DURATION / CLASSIFICATION_WINDOW)  # 30
RESULT_DISPLAY_DURATION = 1.0

# Common cue geometry for Calibration, online Dynamic Fading, and offline MI.
# The exact dimensions follow the original protocol4.py offline cue.
CUE_RADIUS = 0.035
CUE_LEFT_ARROW_VERTICES = [
    (-0.005, 0.014), (-0.060, 0.014), (-0.060, 0.032),
    (-0.105, 0.0), (-0.060, -0.032), (-0.060, -0.014), (-0.005, -0.014),
]
CUE_RIGHT_ARROW_VERTICES = [
    (0.005, 0.014), (0.060, 0.014), (0.060, 0.032),
    (0.105, 0.0), (0.060, -0.032), (0.060, -0.014), (0.005, -0.014),
]



class ExperimentAbort(Exception):
    """Raised when Escape is pressed."""


# =============================================================================
# Command-line arguments
# =============================================================================
def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Adaptive OLD/NEW-A Dynamic Fading with calibration retry and offline fallback. "
            "Frozen preprocessing/feature extraction/classifier settings are read from each participant joblib."
        )
    )
    parser.add_argument("-n", "--name", dest="device_name", required=True)
    parser.add_argument("-f", "--filename", dest="filename", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("-m", "--model-file", required=True)
    parser.add_argument("--model-dir", default="models")
    parser.add_argument("-o", "--outdir", default="data")
    parser.add_argument("--timestamp", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--screen", type=int, default=0)
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument(
        "--offline-features", default=None,
        help="Verified .npz cache of original offline TRAINING features, labels, and trial_ids; "
             "required for 80:20 NEW-A (unless joblib contains adaptation_training).",
    )
    return parser.parse_args()


# =============================================================================
# Trial schedules
# =============================================================================
def make_balanced_target_schedule(n_trials: int, block_size: int, seed: int | None = None) -> list[str]:
    if n_trials <= 0 or block_size <= 0:
        raise ValueError("n_trials and block_size must be positive.")
    if n_trials % block_size != 0 or block_size % 2 != 0:
        raise ValueError("Each block must be even and N_TRIALS must be divisible by block size.")
    rng = random.Random(seed)
    half = block_size // 2
    schedule = []
    for _ in range(n_trials // block_size):
        block = ["LEFT"] * half + ["RIGHT"] * half
        rng.shuffle(block)
        schedule.extend(block)
    return schedule



# =============================================================================
# Trial-level quality / selection metrics
# =============================================================================
def trial_gate_metrics(y_true: np.ndarray, prob_right: np.ndarray, threshold: float) -> dict:
    y_true = np.asarray(y_true, dtype=int).reshape(-1)
    prob_right = np.asarray(prob_right, dtype=float).reshape(-1)
    if len(y_true) != len(prob_right) or set(np.unique(y_true)) != {0, 1}:
        raise ValueError("Quality Gate requires matching balanced LEFT/RIGHT trial data.")
    if not np.isfinite(prob_right).all() or not (0.0 <= threshold <= 1.0):
        raise ValueError("Invalid trial probabilities or threshold.")
    predicted = (prob_right >= threshold).astype(int)
    rec_left = float(recall_score(y_true, predicted, pos_label=0, zero_division=0))
    rec_right = float(recall_score(y_true, predicted, pos_label=1, zero_division=0))
    auc = float(roc_auc_score(y_true, prob_right))
    delta = float(prob_right[y_true == 1].mean() - prob_right[y_true == 0].mean())
    passed = (auc >= GATE_MIN_AUC and delta > GATE_MIN_DELTA_P
              and rec_left >= GATE_MIN_LEFT_RECALL and rec_right >= GATE_MIN_RIGHT_RECALL)
    return {
        "threshold": float(threshold), "auc": auc, "delta_p": delta,
        "left_recall": rec_left, "right_recall": rec_right,
        "ba": float((rec_left + rec_right) / 2),
        "accuracy": float(np.mean(predicted == y_true)),
        "passed": bool(passed),
    }


def choose_model(old_gate: dict, new_gate: dict) -> str | None:
    """Select highest BA among models passing all four gates; OLD wins exact ties."""
    if old_gate["passed"] and new_gate["passed"]:
        return "NEW-A" if new_gate["ba"] > old_gate["ba"] + 1e-12 else "OLD"
    if old_gate["passed"]:
        return "OLD"
    if new_gate["passed"]:
        return "NEW-A"
    return None


# =============================================================================
# Bundle loading / validation
# =============================================================================
def resolve_model_path(model_file: str, model_dir: str) -> Path:
    requested = Path(model_file).expanduser()
    script_dir = Path(__file__).resolve().parent
    if requested.is_absolute() or requested.parent != Path("."):
        candidates = [requested]
        if not requested.is_absolute():
            candidates.append(script_dir / requested)
    else:
        candidates = [
            Path(model_dir).expanduser() / requested.name,
            script_dir / model_dir / requested.name,
            script_dir / requested.name,
        ]
    seen = set()
    searched = []
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        searched.append(candidate)
        if candidate.exists():
            if candidate.suffix.lower() != ".joblib":
                raise ValueError(f"Model must be .joblib: {candidate}")
            return candidate
    raise FileNotFoundError(
        f"Could not find model {model_file!r}. Searched:\n  - "
        + "\n  - ".join(str(p) for p in searched)
    )


def _extract_offline_threshold(bundle: dict) -> float:
    """Read the participant's offline threshold without assuming one bundle schema."""
    predictor = bundle.get("predictor", {})
    value = predictor.get("threshold", 0.5)
    if isinstance(value, dict):
        for key in ("selected_value", "value", "threshold"):
            if key in value:
                return float(value[key])
        raise ValueError("predictor.threshold is a dict but has no usable threshold value.")
    return float(value)


def load_bundle(subject: str, model_file: str, model_dir: str):
    model_path = resolve_model_path(model_file, model_dir)
    bundle = joblib.load(model_path)
    if not isinstance(bundle, dict):
        raise TypeError("The selected joblib is not a bundle dictionary.")

    bundled_subject = str(bundle.get("participant", "")).strip().lower()
    requested_subject = subject.strip().lower()
    if bundled_subject and bundled_subject != requested_subject:
        raise ValueError(
            f"Subject mismatch: --subject={requested_subject!r}, "
            f"bundle participant={bundled_subject!r}."
        )

    validate_bundle_structure(bundle)
    return model_path, bundle


def validate_bundle_structure(bundle: dict) -> None:
    """Validate only experiment-wide requirements; do not impose WMJ's pipeline."""
    required = {"sampling_rate", "input", "preprocessing", "epoch", "predictor", "output"}
    missing = sorted(required.difference(bundle))
    if missing:
        raise KeyError(f"Bundle missing common keys: {missing}")

    fs = float(bundle["sampling_rate"])
    if not np.isfinite(fs) or fs <= 0:
        raise ValueError(f"Invalid sampling rate: {fs}")

    # This experiment always classifies 0.5-s live windows. The participant model
    # may use any channels/filter/feature pipeline, but its model input duration
    # must therefore also be 0.5 s.
    expected_samples = int(round(CLASSIFICATION_WINDOW * fs))
    epoch_samples = int(bundle["epoch"].get("n_samples", expected_samples))
    if epoch_samples != expected_samples:
        raise ValueError(
            f"This neurofeedback protocol uses {CLASSIFICATION_WINDOW:.1f}-s windows "
            f"({expected_samples} samples at {fs:g} Hz), but this joblib expects "
            f"{epoch_samples} samples. Regenerate/choose a compatible online model."
        )

    input_spec = bundle["input"]
    for key in ("all_channel_names", "selected_channel_indices", "selected_channels"):
        if key not in input_spec:
            raise KeyError(f"bundle['input'] is missing {key!r}.")

    predictor = bundle["predictor"]
    if not isinstance(predictor.get("objects", {}), dict):
        raise ValueError("predictor.objects must be a dictionary.")

    output = bundle["output"]
    for key in ("left_label", "right_label", "label_to_direction"):
        if key not in output:
            raise KeyError(f"bundle['output'] is missing {key!r}.")

    # Threshold is required because OLD threshold comparison is part of the protocol.
    _extract_offline_threshold(bundle)


# =============================================================================
# Bundle-driven real-time EEG processor
# =============================================================================
class BundleRuntime:
    """Apply each participant's frozen joblib pipeline without WMJ-specific assumptions.

    Supported bundle styles:
      1) Ordered-object bundles (e.g. clipping/CSP/scaler/classifier stored separately)
         - order is read from bundle['feature_pipeline']['order'] when available.
         - clipping percentiles/ranges are NEVER hard-coded; stored bounds are used.
      2) Legacy sklearn_pipeline bundles
         - all fitted steps except the final classifier are reused as frozen features.
      3) Legacy hybrid_fbriemann_csp bundles
         - fitted covariance/CSP/scaler state is reused exactly as stored.
      4) Generic feature_transformer + classifier bundles
         - feature_transformer.transform() is reused directly.

    If a participant joblib contains an unknown feature step, the code stops with a
    clear error rather than silently substituting WMJ's pipeline.
    """

    def __init__(self, bundle: dict):
        self.bundle = bundle
        self.fs = float(bundle["sampling_rate"])
        self.input_spec = bundle["input"]
        self.operations = list(bundle.get("preprocessing", {}).get("operations", []))
        self.epoch_spec = bundle["epoch"]
        self.predictor = bundle["predictor"]
        self.output_spec = bundle["output"]
        self.feature_spec = bundle.get("feature_pipeline", {}) or {}

        self.all_channel_names = list(self.input_spec["all_channel_names"])
        self.selected_channel_indices = [int(i) for i in self.input_spec["selected_channel_indices"]]
        self.selected_channels = list(self.input_spec["selected_channels"])

        self.predictor_kind = str(self.predictor.get("kind", "")).strip()
        self.objects = dict(self.predictor.get("objects", {}))

        self.clip_enabled = False
        self.clip_lower = None
        self.clip_upper = None
        self.clip_description = "none"
        self._configure_clipping()
        self._configure_predictor_adapter()

        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._chunks: list[np.ndarray] = []
        self._chunk_starts: list[int] = []
        self._sample_count = 0
        self._filter_zi: dict[object, np.ndarray] = {}
        self._stream_error: Exception | None = None
        self._validate_supported_operations()

    # ------------------------------------------------------------------
    # Joblib feature/classifier adapter
    # ------------------------------------------------------------------
    @staticmethod
    def _normalized_name(value: object) -> str:
        return "".join(ch.lower() for ch in str(value) if ch.isalnum())

    def _configure_clipping(self) -> None:
        clip = self.bundle.get("clipping")
        if not isinstance(clip, dict) or not bool(clip.get("enabled", False)):
            return

        lower = clip.get("lower_bounds")
        upper = clip.get("upper_bounds")
        if lower is None or upper is None:
            raise ValueError("Clipping is enabled in joblib but lower/upper bounds are missing.")

        def convert_bounds(value, name):
            if isinstance(value, dict):
                missing = [ch for ch in self.selected_channels if ch not in value]
                if missing:
                    raise ValueError(f"{name} clipping bounds missing channels: {missing}")
                arr = np.asarray([float(value[ch]) for ch in self.selected_channels], dtype=float)
            else:
                arr = np.asarray(value, dtype=float).reshape(-1)
            if arr.shape != (len(self.selected_channels),):
                raise ValueError(
                    f"{name} clipping bounds shape {arr.shape}; expected "
                    f"({len(self.selected_channels)},)."
                )
            return arr

        self.clip_lower = convert_bounds(lower, "lower")
        self.clip_upper = convert_bounds(upper, "upper")
        if not np.isfinite(self.clip_lower).all() or not np.isfinite(self.clip_upper).all():
            raise ValueError("Clipping bounds contain NaN/Inf.")
        if np.any(self.clip_lower >= self.clip_upper):
            raise ValueError("Invalid clipping bounds: lower >= upper.")

        self.clip_enabled = True
        method = str(clip.get("method", "stored_bounds"))
        lo_p = clip.get("lower_percentile")
        hi_p = clip.get("upper_percentile")
        if lo_p is not None and hi_p is not None:
            self.clip_description = f"{method} (P{float(lo_p):g}-P{float(hi_p):g}, stored bounds)"
        else:
            self.clip_description = f"{method} (stored bounds)"

    def _configure_predictor_adapter(self) -> None:
        kind = self.predictor_kind

        # Newer ordered-object bundle: final classifier stored separately and
        # feature order supplied by joblib metadata.
        if self.objects.get("classifier") is not None:
            self.adapter_mode = "ordered_objects"
            self.old_classifier = self.objects["classifier"]
            order = list(self.feature_spec.get("order", []))
            if order:
                self.feature_order = order
            else:
                # Backward-compatible fallback based solely on objects actually present.
                # No percentile, channel, or numeric clipping assumption is introduced.
                self.feature_order = []
                if self.clip_enabled:
                    self.feature_order.append("clipping")
                if self.objects.get("feature_transformer") is not None:
                    self.feature_order.append("feature_transformer")
                else:
                    if self.objects.get("csp") is not None:
                        self.feature_order.append("csp")
                    if self.objects.get("scaler") is not None:
                        self.feature_order.append("scaler")
                self.feature_order.append("classifier")
            self.pipeline_description = " -> ".join(map(str, self.feature_order))

        elif kind == "sklearn_pipeline":
            self.adapter_mode = "sklearn_pipeline"
            model = self.objects.get("model")
            if model is None or not hasattr(model, "steps") or len(model.steps) < 1:
                raise ValueError("sklearn_pipeline bundle requires predictor.objects.model.steps.")
            self.pipeline_model = model
            self.old_classifier = model.steps[-1][1]
            self.pipeline_description = " -> ".join(name for name, _ in model.steps)

        elif kind == "hybrid_fbriemann_csp":
            self.adapter_mode = "hybrid_fbriemann_csp"
            model = self.objects.get("model")
            if model is None:
                raise ValueError("hybrid_fbriemann_csp bundle requires predictor.objects.model.")
            if self.objects.get("feature_state") is None:
                raise ValueError("hybrid_fbriemann_csp bundle requires feature_state.")
            self.old_classifier = model
            scaler_text = " -> scaler" if self.objects.get("scaler") is not None else ""
            self.pipeline_description = f"hybrid_fbriemann_csp{scaler_text} -> classifier"

        elif self.objects.get("feature_transformer") is not None and self.objects.get("model") is not None:
            self.adapter_mode = "feature_transformer"
            self.feature_transformer = self.objects["feature_transformer"]
            self.old_classifier = self.objects["model"]
            self.pipeline_description = "feature_transformer -> classifier"

        else:
            raise NotImplementedError(
                "Unsupported participant predictor structure. The code will not guess a pipeline. "
                f"predictor.kind={kind!r}, object keys={sorted(self.objects)}"
            )

        if not hasattr(self.old_classifier, "fit"):
            raise TypeError("Final classifier must provide fit() so a NEW daily head can be trained.")
        if not hasattr(self.old_classifier, "predict_proba"):
            raise TypeError(
                "Final classifier must provide predict_proba() because this protocol compares "
                "probability thresholds for NEW and OLD classifiers."
            )

    def _validate_supported_operations(self):
        supported = {
            "select_channels",
            "unit_scale",
            "sos_filter",
            "sos_filter_bank",
            "car_reference",
        }
        bad = []
        for op in self.operations:
            scope = op.get("scope", "stream")
            name = op.get("op")
            if scope != "stream" or name not in supported:
                bad.append(f"{name} (scope={scope})")
        if bad:
            raise NotImplementedError(
                "Unsupported joblib stream preprocessing: " + ", ".join(bad)
            )

    def pipeline_summary(self) -> str:
        return self.pipeline_description

    # ------------------------------------------------------------------
    # Live continuous preprocessing
    # ------------------------------------------------------------------
    def reset(self):
        with self._condition:
            self._chunks.clear()
            self._chunk_starts.clear()
            self._sample_count = 0
            self._filter_zi.clear()
            self._stream_error = None
            self._condition.notify_all()

    @property
    def sample_count(self) -> int:
        with self._lock:
            return int(self._sample_count)

    def set_stream_error(self, exc: Exception):
        with self._condition:
            self._stream_error = exc
            self._condition.notify_all()

    def process_packet(self, packet):
        try:
            _, exg_data = packet.get_data()
            data = self._normalize_packet_shape(exg_data)
            processed = self._apply_stream_operations(data)
            if processed.size == 0:
                return
            with self._condition:
                processed = np.asarray(processed, dtype=np.float64)
                self._chunk_starts.append(int(self._sample_count))
                self._chunks.append(processed)
                self._sample_count += int(processed.shape[0])
                self._condition.notify_all()
        except Exception as exc:
            self.set_stream_error(exc)

    def _normalize_packet_shape(self, exg_data) -> np.ndarray:
        arr = np.asarray(exg_data, dtype=np.float64)
        if arr.ndim != 2:
            raise ValueError(f"Unexpected ExG packet shape: {arr.shape}")
        n_expected = len(self.all_channel_names)

        # Explorepy delivers ExG packets as (n_channels, n_samples), e.g. (16, 1) or (8, 1).
        # We need (n_samples, n_channels).
        if arr.shape[0] in (4, 8, 16, 32) and arr.shape[0] != arr.shape[1]:
            arr = arr.T
        elif arr.shape[0] == n_expected and arr.shape[1] != n_expected:
            arr = arr.T
        elif arr.shape[1] == n_expected:
            pass
        elif arr.shape[0] <= 32 and arr.shape[1] > arr.shape[0]:
            arr = arr.T

        # When hardware transmits 16 channels but channels 9-16 are broken/shorted,
        # slice to expected channels (1~8) BEFORE NaN/Inf check so shorted channels are ignored.
        if arr.shape[1] > n_expected:
            arr = arr[:, :n_expected]

        if arr.shape[1] < n_expected:
            raise ValueError(
                f"Bundle expects {n_expected} channels, but incoming packet has only {arr.shape[1]} channels."
            )
        if not np.isfinite(arr).all():
            raise ValueError("Incoming EEG (in selected channels) contains NaN/Inf.")
        return arr

    def _apply_stream_operations(self, data: np.ndarray) -> np.ndarray:
        y = np.asarray(data, dtype=np.float64)
        for op_index, operation in enumerate(self.operations):
            name = operation["op"]
            params = operation.get("params", {})

            if name == "select_channels":
                indices = [int(i) for i in params["indices"]]
                if y.ndim == 2:
                    y = y[:, indices]
                elif y.ndim == 3:
                    y = y[:, :, indices]
                else:
                    raise ValueError(f"select_channels cannot handle shape {y.shape}")

            elif name == "unit_scale":
                y = y * float(params["factor"])

            elif name == "car_reference":
                if y.ndim == 2:
                    y = y - np.mean(y, axis=1, keepdims=True)
                elif y.ndim == 3:
                    y = y - np.mean(y, axis=2, keepdims=True)
                else:
                    raise ValueError(f"car_reference cannot handle shape {y.shape}")

            elif name == "sos_filter":
                if y.ndim != 2:
                    raise ValueError("sos_filter expects samples x channels before filter-bank expansion.")
                sos = np.asarray(params["sos"], dtype=np.float64)
                zi = self._filter_zi.get(op_index)
                if zi is None:
                    zi = np.zeros((sos.shape[0], 2, y.shape[1]), dtype=np.float64)
                y, zf = sosfilt(sos, y, axis=0, zi=zi)
                self._filter_zi[op_index] = zf

            elif name == "sos_filter_bank":
                if y.ndim != 2:
                    raise ValueError("sos_filter_bank expects samples x channels input.")
                sos_list = [np.asarray(v, dtype=np.float64) for v in params["sos_list"]]
                band_outputs = []
                for band_index, sos in enumerate(sos_list):
                    key = (op_index, band_index)
                    zi = self._filter_zi.get(key)
                    if zi is None:
                        zi = np.zeros((sos.shape[0], 2, y.shape[1]), dtype=np.float64)
                    band_y, zf = sosfilt(sos, y, axis=0, zi=zi)
                    self._filter_zi[key] = zf
                    band_outputs.append(band_y)
                # samples x bands x channels
                y = np.stack(band_outputs, axis=1)

            else:
                raise NotImplementedError(f"Unsupported stream op: {name}")

        expected_n = len(self.selected_channels)
        if y.ndim == 2:
            channel_count = y.shape[1]
            if channel_count != expected_n:
                if channel_count == len(self.all_channel_names):
                    y = y[:, self.selected_channel_indices]
                else:
                    raise ValueError(
                        f"Processed channel count {channel_count} != expected {expected_n}."
                    )
        elif y.ndim == 3:
            channel_count = y.shape[2]
            if channel_count != expected_n:
                if channel_count == len(self.all_channel_names):
                    y = y[:, :, self.selected_channel_indices]
                else:
                    raise ValueError(
                        f"Processed filter-bank channel count {channel_count} != expected {expected_n}."
                    )
        else:
            raise ValueError(f"Unexpected processed EEG shape {y.shape}")
        return y

    def mark_stream_sample(self) -> int:
        with self._lock:
            if self._stream_error is not None:
                raise RuntimeError("EEG stream callback failed") from self._stream_error
            return int(self._sample_count)

    def _slice_samples_locked(self, start: int, stop: int) -> np.ndarray:
        if start < 0 or stop <= start:
            raise ValueError(f"Invalid sample range {start}:{stop}")
        if not self._chunks:
            raise RuntimeError("No EEG samples available.")
        idx = max(0, bisect_right(self._chunk_starts, start) - 1)
        parts = []
        cursor = start
        while idx < len(self._chunks) and cursor < stop:
            chunk = self._chunks[idx]
            chunk_start = self._chunk_starts[idx]
            chunk_stop = chunk_start + int(chunk.shape[0])
            if chunk_stop <= cursor:
                idx += 1
                continue
            if chunk_start > cursor:
                raise RuntimeError(f"Gap in EEG stream at sample {cursor}.")
            local_start = cursor - chunk_start
            local_stop = min(stop, chunk_stop) - chunk_start
            parts.append(chunk[local_start:local_stop])
            cursor = chunk_start + local_stop
            idx += 1
        if cursor != stop:
            raise RuntimeError(f"Could not assemble samples {start}:{stop}; reached {cursor}.")
        return np.concatenate(parts, axis=0)

    def get_processed_segment(self, start_sample: int, n_samples: int, timeout: float = 2.0) -> np.ndarray:
        start = int(start_sample)
        stop = start + int(n_samples)
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._sample_count < stop:
                if self._stream_error is not None:
                    raise RuntimeError("EEG stream callback failed") from self._stream_error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Need sample {stop}, currently have {self._sample_count}.")
                self._condition.wait(timeout=min(0.05, remaining))
            segment = self._slice_samples_locked(start, stop)

        n_channels = len(self.selected_channels)
        if segment.ndim == 2 and segment.shape != (int(n_samples), n_channels):
            raise RuntimeError(
                f"Segment shape {segment.shape}; expected ({int(n_samples)}, {n_channels})."
            )
        if segment.ndim == 3 and (
            segment.shape[0] != int(n_samples) or segment.shape[2] != n_channels
        ):
            raise RuntimeError(
                f"Filter-bank segment shape {segment.shape}; expected samples x bands x {n_channels}."
            )
        if segment.ndim not in {2, 3}:
            raise RuntimeError(f"Unexpected segment shape {segment.shape}")
        return np.asarray(segment, dtype=np.float64)

    def get_window_epoch(self, start_sample: int, n_samples: int, timeout: float = 2.0) -> np.ndarray:
        expected_samples = int(self.epoch_spec.get("n_samples", round(CLASSIFICATION_WINDOW * self.fs)))
        if int(n_samples) != expected_samples:
            raise ValueError(f"Requested {n_samples} samples, model expects {expected_samples}.")
        segment = self.get_processed_segment(start_sample, n_samples, timeout=timeout)
        if segment.ndim == 2:
            return segment.T[np.newaxis, :, :]  # batch x channels x time
        return np.transpose(segment, (1, 2, 0))[np.newaxis, :, :, :]  # batch x bands x channels x time

    # ------------------------------------------------------------------
    # Frozen feature extraction driven by participant joblib
    # ------------------------------------------------------------------
    def _apply_stored_clipping(self, x: np.ndarray) -> np.ndarray:
        if not self.clip_enabled:
            return np.asarray(x, dtype=np.float64)
        x = np.asarray(x, dtype=np.float64)
        if x.ndim == 3:  # batch x channels x time
            if x.shape[1] != len(self.selected_channels):
                raise ValueError(f"Clipping channel mismatch: {x.shape}")
            return np.clip(
                x,
                self.clip_lower[None, :, None],
                self.clip_upper[None, :, None],
            )
        if x.ndim == 4:  # batch x bands x channels x time
            if x.shape[2] != len(self.selected_channels):
                raise ValueError(f"Filter-bank clipping channel mismatch: {x.shape}")
            return np.clip(
                x,
                self.clip_lower[None, None, :, None],
                self.clip_upper[None, None, :, None],
            )
        raise ValueError(f"Stored channel clipping cannot be applied to shape {x.shape}")

    @staticmethod
    def _apply_scaler_to_array(scaler, x: np.ndarray) -> np.ndarray:
        """Apply a fitted scaler while respecting how many features it was fit on."""
        x = np.asarray(x, dtype=np.float64)
        if x.ndim == 2:
            return np.asarray(scaler.transform(x), dtype=np.float64)

        n_features = getattr(scaler, "n_features_in_", None)
        if x.ndim == 3:
            n, c, t = x.shape
            if n_features == c:
                flat = np.transpose(x, (0, 2, 1)).reshape(-1, c)
                z = np.asarray(scaler.transform(flat), dtype=np.float64)
                return np.transpose(z.reshape(n, t, c), (0, 2, 1))
            if n_features == c * t:
                return np.asarray(scaler.transform(x.reshape(n, c * t)), dtype=np.float64).reshape(n, c, t)

        # Let custom sklearn-compatible transformers decide if they support the shape.
        try:
            return np.asarray(scaler.transform(x), dtype=np.float64)
        except Exception as exc:
            raise RuntimeError(
                f"Stored scaler {type(scaler).__name__} cannot transform array shape {x.shape}; "
                "the participant joblib needs an explicit compatible feature transformer/order."
            ) from exc

    def _resolve_ordered_object(self, step_name: str):
        object_map = self.feature_spec.get("object_map", {})
        if isinstance(object_map, dict) and step_name in object_map:
            key = object_map[step_name]
            if key not in self.objects:
                raise KeyError(f"feature_pipeline.object_map maps {step_name!r} -> missing {key!r}")
            return key, self.objects[key]

        normalized = self._normalized_name(step_name)
        # Direct object-key match first.
        for key, obj in self.objects.items():
            if self._normalized_name(key) == normalized:
                return key, obj

        # Scaler-like names are checked before CSP because names such as
        # "CSP_component_MinMaxScaler" contain both tokens.
        if any(token in normalized for token in ("scaler", "minmax", "standardscale", "robustscale", "zscore")):
            if self.objects.get("scaler") is not None:
                return "scaler", self.objects["scaler"]
        if "csp" in normalized and self.objects.get("csp") is not None:
            return "csp", self.objects["csp"]
        if "featuretransform" in normalized and self.objects.get("feature_transformer") is not None:
            return "feature_transformer", self.objects["feature_transformer"]
        return None, None

    @staticmethod
    def _is_classifier_step(step_name: str) -> bool:
        normalized = "".join(ch.lower() for ch in str(step_name) if ch.isalnum())
        return any(token in normalized for token in (
            "classifier", "lda", "svc", "svm", "logistic", "randomforest",
            "xgboost", "lightgbm", "knn", "naivebayes",
        ))

    def _ordered_features(self, epochs: np.ndarray) -> np.ndarray:
        x = np.asarray(epochs, dtype=np.float64)
        clipping_applied = False
        transformed_any = False

        for step in self.feature_order:
            normalized = self._normalized_name(step)
            if self._is_classifier_step(step):
                continue
            if "clip" in normalized:
                if not self.clip_enabled:
                    raise RuntimeError(
                        f"feature_pipeline requests clipping step {step!r}, but joblib clipping is disabled/missing."
                    )
                x = self._apply_stored_clipping(x)
                clipping_applied = True
                transformed_any = True
                continue

            key, obj = self._resolve_ordered_object(step)
            if obj is None:
                raise NotImplementedError(
                    f"Unsupported feature step {step!r} in participant joblib. "
                    "Add feature_pipeline.object_map or a supported fitted transformer; "
                    "the runtime will not substitute another participant's pipeline."
                )

            if key == "scaler":
                x = self._apply_scaler_to_array(obj, x)
            else:
                if not hasattr(obj, "transform"):
                    raise TypeError(f"Stored feature object {key!r} has no transform().")
                x = np.asarray(obj.transform(x), dtype=np.float64)
            transformed_any = True

        # If clipping exists but the order metadata did not mention it, apply it only
        # for legacy ordered-object bundles before their first feature transform.
        if self.clip_enabled and not clipping_applied and not self.feature_spec.get("order"):
            x0 = self._apply_stored_clipping(np.asarray(epochs, dtype=np.float64))
            x = x0
            for step in self.feature_order:
                if self._is_classifier_step(step) or "clip" in self._normalized_name(step):
                    continue
                key, obj = self._resolve_ordered_object(step)
                if obj is None:
                    continue
                if key == "scaler":
                    x = self._apply_scaler_to_array(obj, x)
                else:
                    x = np.asarray(obj.transform(x), dtype=np.float64)
            transformed_any = True

        if not transformed_any:
            raise RuntimeError("No frozen feature transform was applied before classifier training.")
        if x.ndim != 2:
            raise RuntimeError(
                f"Frozen feature pipeline ended with shape {x.shape}, but classifier features must be 2-D."
            )
        return np.asarray(x, dtype=np.float64)

    @staticmethod
    def _compute_shrinkage_covariances(X: np.ndarray, shrink: float) -> np.ndarray:
        n_trials, n_channels, n_times = X.shape
        centered = X - np.mean(X, axis=2, keepdims=True)
        covs = np.einsum("nct,ndt->ncd", centered, centered) / max(1, n_times - 1)
        eye = np.eye(n_channels)
        traces = np.trace(covs, axis1=1, axis2=2)[:, None, None]
        return (1.0 - shrink) * covs + shrink * (traces / float(n_channels)) * eye

    @staticmethod
    def _vectorized_tangent_space(covs: np.ndarray, ref_cov: np.ndarray) -> np.ndarray:
        n_trials, n_channels, _ = covs.shape
        m_vals, m_vecs = np.linalg.eigh(ref_cov)
        inv_sqrt_vals = 1.0 / np.sqrt(np.maximum(m_vals, 1e-10))
        c_inv_sqrt = np.einsum("ij,j,kj->ik", m_vecs, inv_sqrt_vals, m_vecs)
        transformed = np.einsum("ij,njk,kl->nil", c_inv_sqrt, covs, c_inv_sqrt)
        t_vals, t_vecs = np.linalg.eigh(transformed)
        log_t_vals = np.log(np.maximum(t_vals, 1e-10))
        s_covs = np.einsum("nij,nj,nkj->nik", t_vecs, log_t_vals, t_vecs)
        triu_i, triu_j = np.triu_indices(n_channels)
        weights = np.where(triu_i == triu_j, 1.0, np.sqrt(2.0))
        return s_covs[:, triu_i, triu_j] * weights[None, :]

    def _hybrid_features(self, epochs: np.ndarray) -> np.ndarray:
        x = self._apply_stored_clipping(epochs) if self.clip_enabled else np.asarray(epochs, dtype=float)
        if x.ndim != 4:
            raise ValueError(
                f"hybrid_fbriemann_csp expects batch x bands x channels x time, got {x.shape}."
            )
        state = self.objects["feature_state"]
        shrink = float(state["shrink"])
        ref_covs = state["ref_covs"]
        csps = state["csps"]
        n_bands = x.shape[1]
        if len(ref_covs) != n_bands or len(csps) != n_bands:
            raise RuntimeError("Hybrid feature_state band count does not match live epoch.")

        ts_features = []
        csp_features = []
        for b in range(n_bands):
            X_b = x[:, b, :, :]
            covs = self._compute_shrinkage_covariances(X_b, shrink)
            ts_features.append(
                self._vectorized_tangent_space(covs, np.asarray(ref_covs[b], dtype=float))
            )
            csp_features.append(csps[b].transform(X_b))
        features = np.hstack([np.hstack(ts_features), np.hstack(csp_features)])
        scaler = self.objects.get("scaler")
        if scaler is not None:
            features = scaler.transform(features)
        return np.asarray(features, dtype=np.float64)

    def extract_frozen_features(self, epochs: np.ndarray) -> np.ndarray:
        """Return classifier-ready features using this participant's frozen joblib."""
        if self.adapter_mode == "ordered_objects":
            return self._ordered_features(epochs)

        if self.adapter_mode == "sklearn_pipeline":
            x = self._apply_stored_clipping(epochs) if self.clip_enabled else np.asarray(epochs, dtype=float)
            frozen = self.pipeline_model[:-1]
            features = frozen.transform(x)
            return np.asarray(features, dtype=np.float64)

        if self.adapter_mode == "hybrid_fbriemann_csp":
            return self._hybrid_features(epochs)

        if self.adapter_mode == "feature_transformer":
            x = self._apply_stored_clipping(epochs) if self.clip_enabled else np.asarray(epochs, dtype=float)
            return np.asarray(self.feature_transformer.transform(x), dtype=np.float64)

        raise RuntimeError(f"Unknown adapter mode: {self.adapter_mode}")

    def right_probabilities_from_features(self, classifier, features: np.ndarray) -> np.ndarray:
        if not hasattr(classifier, "predict_proba"):
            raise TypeError(
                f"{type(classifier).__name__} has no predict_proba(); probability thresholding is required."
            )
        proba = np.asarray(classifier.predict_proba(features), dtype=np.float64)
        classes = np.asarray(classifier.classes_)
        right_label = self.output_spec["right_label"]
        match = np.flatnonzero(classes == right_label)
        if len(match) != 1:
            raise RuntimeError(f"RIGHT label {right_label!r} not found in classes {classes}.")
        return proba[:, int(match[0])]

    def predict_with_classifier(self, epoch: np.ndarray, classifier, threshold: float):
        features = self.extract_frozen_features(epoch)
        p_right = float(self.right_probabilities_from_features(classifier, features)[0])
        left_label = self.output_spec["left_label"]
        right_label = self.output_spec["right_label"]
        label = right_label if p_right >= float(threshold) else left_label
        direction = self.output_spec["label_to_direction"].get(label)
        if direction is None:
            direction = self.output_spec["label_to_direction"].get(str(label))
        if direction is None:
            raise KeyError(f"Label {label!r} missing from label_to_direction.")
        return label, str(direction).upper(), p_right


# =============================================================================
# Verified original offline training features + weighted shrinkage LDA
# =============================================================================
def model_file_sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def _validate_offline_training_cache(cache: dict, runtime: BundleRuntime, model_hash: str, subject: str):
    """Reject unrelated or unverifiable caches, rather than quietly training NEW-B."""
    for key in ("features", "labels", "trial_ids", "participant", "model_sha256"):
        if key not in cache:
            raise ValueError(f"Offline training cache is missing required key {key!r}.")
    participant = str(np.asarray(cache["participant"]).item()).strip().lower()
    sha = str(np.asarray(cache["model_sha256"]).item()).strip().lower()
    if participant != subject or sha != model_hash:
        raise ValueError("Offline features do not match the participant/joblib file. "
                         "Re-export original TRAINING features using this exact frozen joblib.")
    x = np.asarray(cache["features"], dtype=np.float64)
    y = np.asarray(cache["labels"]).reshape(-1)
    trial_ids = np.asarray(cache["trial_ids"]).reshape(-1)
    feature_dim = getattr(runtime.old_classifier, "n_features_in_", None)
    if feature_dim is None:
        raise ValueError("The old classifier has no n_features_in_: feature dimension cannot be validated.")
    if x.ndim != 2 or x.shape[1] != int(feature_dim) or len(x) != len(y) or len(x) != len(trial_ids):
        raise ValueError(f"Offline feature/label/trial-id size mismatch or wrong feature dimension: {x.shape}.")
    if len(x) < 4 or not np.isfinite(x).all():
        raise ValueError("Offline features are missing or non-finite.")
    allowed = set(runtime.old_classifier.classes_)
    if set(np.unique(y)) != allowed:
        raise ValueError(f"Offline label classes {np.unique(y)} != model classes {allowed}.")
    for tid in np.unique(trial_ids):
        if len(np.unique(y[trial_ids == tid])) != 1:
            raise ValueError(f"Offline trial ID {tid!r} contains mixed class labels.")
    return x, y, trial_ids


def load_offline_training_data(args, runtime: BundleRuntime, bundle: dict, model_path: Path):
    model_hash = model_file_sha256(model_path)
    if args.offline_features:
        path = Path(args.offline_features).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Offline training feature cache not found: {path}")
        with np.load(path, allow_pickle=False) as f:
            cache = {key: f[key] for key in f.files}
        return _validate_offline_training_cache(cache, runtime, model_hash, args.subject.strip().lower())
    if "adaptation_training" in bundle:
        # Embedded features are from this exact loaded joblib by construction.
        cache = dict(bundle["adaptation_training"])
        cache["participant"] = bundle["participant"]
        cache["model_sha256"] = model_hash
        return _validate_offline_training_cache(cache, runtime, model_hash, args.subject.strip().lower())
    raise FileNotFoundError(
        "NEW-A needs original offline TRAINING features and labels, but this joblib "
        "contains no adaptation_training entry. Supply --offline-features path/to/cache.npz. "
        "Never substitute today's 120 calibration windows for the 80% offline training group."
    )


def trial_equalized_weights(labels: np.ndarray, trial_ids: np.ndarray, group_weight: float,
                            classes: np.ndarray) -> np.ndarray:
    """Class-balanced group mass; every trial has equal mass, its windows share it."""
    labels = np.asarray(labels).reshape(-1)
    trial_ids = np.asarray(trial_ids).reshape(-1)
    if len(labels) != len(trial_ids):
        raise ValueError("labels and trial_ids length mismatch")
    result = np.zeros(len(labels), dtype=np.float64)
    for label in classes:
        class_mask = labels == label
        tids, inverse, counts = np.unique(trial_ids[class_mask], return_inverse=True, return_counts=True)
        if not len(tids):
            raise ValueError(f"Missing class {label!r} in training group")
        # Each class has 50% of this group's total mass.
        result[class_mask] = group_weight * 0.5 / len(tids) / counts[inverse]
    return result


class WeightedLDAHead:
    """Weighted class-balanced LDA with weighted Ledoit-Wolf-like covariance shrinkage.

    scikit-learn LDA(solver='lsqr', shrinkage='auto') has no sample_weight.
    This is a separate, explicitly weighted estimator, not an identical clone of
    sklearn's 'auto' shrinkage. Its probabilities and shrinkage require offline
    numeric validation with representative data before live use.
    """
    def fit(self, features: np.ndarray, labels: np.ndarray, sample_weight: np.ndarray):
        x = np.asarray(features, dtype=np.float64)
        y = np.asarray(labels).reshape(-1)
        w = np.asarray(sample_weight, dtype=np.float64).reshape(-1)
        if x.ndim != 2 or x.shape[0] != len(y) or len(w) != len(y):
            raise ValueError("Weighted LDA feature/label/weight size mismatch")
        if not np.isfinite(x).all() or not np.isfinite(w).all() or np.any(w <= 0):
            raise ValueError("Weighted LDA needs finite features and positive weights")
        self.classes_ = np.unique(y)
        if len(self.classes_) != 2:
            raise ValueError("Weighted LDA requires exactly two classes")
        self.n_features_in_ = x.shape[1]
        means, covariances, shrinkages = [], [], []
        for label in self.classes_:
            z, a = x[y == label], w[y == label]
            a = a / a.sum()
            mean = np.einsum("i,ij->j", a, z)
            centered = z - mean
            std = np.sqrt(np.maximum(np.einsum("i,ij->j", a, centered ** 2), 1e-24))
            standardized = centered / std
            sample_cov = (standardized * a[:, None]).T @ standardized
            p = sample_cov.shape[0]
            mu = float(np.trace(sample_cov) / p)
            deviation = sample_cov - mu * np.eye(p)
            delta = float(np.sum(deviation ** 2))
            if delta <= 1e-20:
                shrinkage = 0.0
            else:
                norm4 = np.sum(standardized ** 2, axis=1) ** 2
                cross = np.einsum("ij,jk,ik->i", standardized, sample_cov, standardized)
                s_norm = float(np.sum(sample_cov ** 2))
                beta = float(np.sum(a ** 2 * np.maximum(norm4 - 2 * cross + s_norm, 0)))
                shrinkage = float(np.clip(beta / delta, 0, 1))
            cov_standardized = ((1 - shrinkage) * sample_cov
                                + shrinkage * mu * np.eye(p))
            covariances.append(cov_standardized * std[:, None] * std[None, :])
            means.append(mean)
            shrinkages.append(shrinkage)
        self.means_ = np.stack(means)
        self.shrinkages_ = tuple(shrinkages)
        # 50:50 class balancing is already encoded in input weights; use it in pooling.
        pooled = 0.5 * (covariances[0] + covariances[1])
        ridge = max(1e-18, float(np.trace(pooled) / self.n_features_in_) * 1e-8)
        self.covariance_ = pooled + ridge * np.eye(self.n_features_in_)
        inv_delta = np.linalg.solve(self.covariance_, means[1] - means[0])
        self.coef_ = inv_delta.reshape(1, -1)
        self.intercept_ = np.array([-0.5 * (means[1] + means[0]) @ inv_delta])
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        x = np.asarray(features, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != self.n_features_in_ or not np.isfinite(x).all():
            raise ValueError("Weighted LDA input feature dimensions or values are invalid")
        z = np.clip(x @ self.coef_[0] + self.intercept_[0], -700, 700)
        p1 = 1.0 / (1.0 + np.exp(-z))
        return np.column_stack([1.0 - p1, p1])


def fit_new_a(runtime: BundleRuntime, x_off, y_off, id_off, x_today, y_today, id_today):
    classes = np.asarray(runtime.old_classifier.classes_)
    w_off = trial_equalized_weights(y_off, id_off, OFFLINE_TRAIN_WEIGHT, classes)
    w_today = trial_equalized_weights(y_today, id_today, DAILY_TRAIN_WEIGHT, classes)
    x = np.vstack([x_off, x_today])
    y = np.concatenate([y_off, y_today])
    weights = np.concatenate([w_off, w_today])
    return WeightedLDAHead().fit(x, y, weights)


def build_new_classifier_and_oof(runtime: BundleRuntime, x_off, y_off, id_off,
                                 x_today, y_today, trial_ids, seed):
    """20 trial-grouped OOF predictions: each fold uses offline + 16 held-in trials."""
    y_today = np.asarray(y_today)
    trial_ids = np.asarray(trial_ids)
    unique_trials = np.unique(trial_ids)
    trial_labels = np.asarray([y_today[trial_ids == tid][0] for tid in unique_trials])
    for tid, label in zip(unique_trials, trial_labels):
        if not np.all(y_today[trial_ids == tid] == label):
            raise ValueError(f"Mixed labels in trial {tid}")
    if len(unique_trials) != CALIBRATION_TRIALS:
        raise ValueError(f"Expected {CALIBRATION_TRIALS} unique calibration trials")
    binary_labels = (trial_labels == runtime.output_spec["right_label"]).astype(int)
    cv = StratifiedKFold(n_splits=CALIBRATION_OOF_FOLDS, shuffle=True,
                         random_state=20261003 if seed is None else int(seed))
    oof = np.full(len(y_today), np.nan)
    for train_idx, test_idx in cv.split(unique_trials, binary_labels):
        train = np.isin(trial_ids, unique_trials[train_idx])
        test = np.isin(trial_ids, unique_trials[test_idx])
        head = fit_new_a(runtime, x_off, y_off, id_off, x_today[train], y_today[train], trial_ids[train])
        oof[test] = runtime.right_probabilities_from_features(head, x_today[test])
    if not np.isfinite(oof).all():
        raise RuntimeError("Incomplete NEW-A 5-fold OOF predictions")
    return oof


def aggregate_trial_probabilities(y_window, trial_ids, p_window, right_label):
    trials = np.unique(trial_ids)
    y_true, scores = [], []
    for tid in trials:
        mask = trial_ids == tid
        labels = np.unique(y_window[mask])
        if len(labels) != 1:
            raise ValueError(f"Trial {tid} has multiple labels")
        y_true.append(int(labels[0] == right_label))
        scores.append(float(np.median(p_window[mask])))
    return np.asarray(y_true, dtype=int), np.asarray(scores, dtype=np.float64)


def basic_eeg_qc(x_cal: np.ndarray) -> dict:
    """Only obvious faults: invalid samples, entire selected channels flat, missing epochs."""
    x = np.asarray(x_cal)
    if x.ndim not in (3, 4) or not np.isfinite(x).all():
        return {"passed": False, "reason": "Invalid EEG epoch shape or NaN/Inf"}
    if x.shape[0] != CALIBRATION_TRIALS * CALIBRATION_WINDOWS_PER_TRIAL:
        return {"passed": False, "reason": "Missing calibration windows"}
    # Epochs are [window,channel,sample] or [window,band,channel,sample].
    time_axis = x.ndim - 1
    channel_axis = x.ndim - 2
    flat_dims = tuple(i for i in range(x.ndim) if i != channel_axis)
    # Exactly constant over the entire calibration, without arbitrary amplitude cutoffs.
    low = np.min(x, axis=flat_dims)
    high = np.max(x, axis=flat_dims)
    if np.any(high == low):
        return {"passed": False, "reason": "A selected EEG channel is flat for the whole calibration"}
    return {"passed": True, "reason": "OK"}


def _csv_float_sequence(values) -> str:
    return ",".join(f"{float(v):.8f}" for v in np.asarray(values).reshape(-1))


# =============================================================================
# Output / timing helpers
# =============================================================================
def build_output_paths(args):
    session_name = Path(args.filename).name
    if args.timestamp:
        session_name = f"{session_name}_{datetime.now():%Y%m%d_%H%M%S}"

    output_dir = Path(args.outdir).expanduser().resolve() / session_name
    output_dir.mkdir(parents=True, exist_ok=True)

    eeg_base = output_dir / session_name
    log_path = output_dir / f"{session_name}_online_trial_log.csv"
    calibration_log_path = output_dir / f"{session_name}_calibration_trial_log.csv"
    calibration_summary_path = output_dir / f"{session_name}_calibration_summary.csv"
    offline_log_path = output_dir / f"{session_name}_offline_trial_log.csv"
    session_log_path = output_dir / f"{session_name}_session_decision.csv"
    return (output_dir, eeg_base, log_path, calibration_log_path,
            calibration_summary_path, offline_log_path, session_log_path)


def check_escape():
    if "escape" in event.getKeys(keyList=["escape"]):
        raise ExperimentAbort


def wait_with_escape(duration: float):
    clock = core.Clock()
    while clock.getTime() < duration:
        check_escape()
        core.wait(0.005)


def wait_for_space(stimulus, win):
    event.clearEvents(eventType="keyboard")
    stimulus.draw()
    win.flip()
    while True:
        keys = event.getKeys(keyList=["space", "escape"])
        if "escape" in keys:
            raise ExperimentAbort
        if "space" in keys:
            return
        core.wait(0.01)


def level_marker(level: int) -> int:
    return {
        0: LEVEL_0_ONSET,
        1: LEVEL_1_ONSET,
        2: LEVEL_2_ONSET,
        3: LEVEL_3_ONSET,
    }[int(level)]


# =============================================================================
# Korean instruction and results screens (independent of real-time cue objects)
# =============================================================================
class _ScreenGroup:
    """Drawable aggregate accepted by the existing wait_for_space() helper."""

    def __init__(self, stimuli):
        self.stimuli = stimuli

    def draw(self):
        for stimulus in self.stimuli:
            stimulus.draw()


class KoreanResultsUI:
    """Compact Korean instruction/results screens for the PsychoPy experiment.

    All text on these screens is the same size. Tables are grouped at screen
    center, while numeric values remain black and pass/fail words are colored.
    Coordinates are PsychoPy norm units (-1..1).
    """

    BLACK = (0, 0, 0)
    GREEN = (0, 140, 65)
    RED = (195, 35, 45)
    TEXT_HEIGHT = 0.056

    def __init__(self, win):
        self.win = win

    def _text(self, items, text, x, y, color=None, width=1.9):
        stim = visual.TextStim(
            self.win, text=str(text), pos=(float(x), float(y)),
            height=self.TEXT_HEIGHT,
            color=self.BLACK if color is None else color,
            colorSpace="rgb255", units="norm", wrapWidth=width,
            font="Malgun Gothic",
        )
        items.append(stim)
        return stim

    def _show(self, items):
        wait_for_space(_ScreenGroup(items), self.win)

    def initial_calibration(self):
        """Show the concise 20-trial Calibration instructions as one group."""
        items = []
        lines = (
            ("Calibration", 0.42),
            ("운동 상상 뇌파 사전 측정", 0.32),
            ("총 20 Trial (LEFT 10 / RIGHT 10)", 0.18),
            ("각 Trial당 운동 상상 3초", 0.075),
            ("10 Trial 종료 후 5초간 휴식", -0.03),
            ("제시되는 방향에 따라 왼손 또는 오른손의 움직임을 상상해 주세요.", -0.18),
            ("SPACE : 측정 시작       ESC : 실험 종료", -0.39),
        )
        for content, y in lines:
            self._text(items, content, 0, y)
        return _ScreenGroup(items)

    @staticmethod
    def _metric_text(value, decimals=3):
        try:
            return f"{float(value):.{decimals}f}" if np.isfinite(float(value)) else "—"
        except (TypeError, ValueError):
            return "—"

    def _gate_rows(self, items, old_gate, new_gate, with_threshold, show_ba):
        """Center a compact table; use separate items for numbers and verdicts."""
        if with_threshold:
            # Four compact columns: metric / threshold / OLD / NEW-A.
            metric_x, criterion_x, old_x, new_x = -0.44, -0.14, 0.17, 0.46
            old_value_x, old_status_x = 0.12, 0.23
            new_value_x, new_status_x = 0.41, 0.52
            header_y, row_top, row_step, summary_y = 0.35, 0.24, 0.105, -0.23
            self._text(items, "평가 항목", metric_x, header_y)
            self._text(items, "통과 기준", criterion_x, header_y)
        else:
            # Compact three-column table: metric / OLD / NEW-A.
            metric_x, old_x, new_x = -0.32, 0.04, 0.32
            old_value_x, old_status_x = -0.015, 0.095
            new_value_x, new_status_x = 0.265, 0.375
            header_y, row_top, row_step, summary_y = 0.39, 0.28, 0.105, -0.20
            self._text(items, "평가 항목", metric_x, header_y)
        self._text(items, "OLD", old_x, header_y)
        self._text(items, "NEW-A", new_x, header_y)

        checks = (
            ("AUC", "≥ 0.60", "auc", lambda v: v >= GATE_MIN_AUC),
            ("ΔP", "> 0.03", "delta_p", lambda v: v > GATE_MIN_DELTA_P),
            ("LEFT Recall", "≥ 0.50", "left_recall", lambda v: v >= GATE_MIN_LEFT_RECALL),
            ("RIGHT Recall", "≥ 0.50", "right_recall", lambda v: v >= GATE_MIN_RIGHT_RECALL),
        )
        for i, (name, criterion, key, check) in enumerate(checks):
            y = row_top - i * row_step
            self._text(items, name, metric_x, y)
            if with_threshold:
                self._text(items, criterion, criterion_x, y)
            for gate, vx, sx in (
                (old_gate, old_value_x, old_status_x),
                (new_gate, new_value_x, new_status_x),
            ):
                value = float(gate[key])
                meets = np.isfinite(value) and bool(check(value))
                self._text(items, self._metric_text(value, decimals=4 if key == "delta_p" else 3), vx, y)
                self._text(items, "통과" if meets else "미달", sx, y,
                           color=self.GREEN if meets else self.RED)

        self._text(items, "최종 결과" if with_threshold else "Quality Gate", metric_x, summary_y)
        if with_threshold:
            self._text(items, "전체 조건 충족", criterion_x, summary_y)
        for gate, x in ((old_gate, old_x), (new_gate, new_x)):
            self._text(items, "PASS" if gate["passed"] else "FAIL", x, summary_y,
                       color=self.GREEN if gate["passed"] else self.RED)
        if show_ba:
            y_ba = -0.31
            self._text(items, "Balanced Accuracy", metric_x, y_ba)
            self._text(items, self._metric_text(old_gate["ba"]), old_x, y_ba)
            self._text(items, self._metric_text(new_gate["ba"]), new_x, y_ba)

    def quality_failure(self, attempt, old_gate, new_gate):
        assert attempt in (1, 2)
        items = []
        self._text(items, f"{attempt}차 Calibration — Quality Gate 미통과", 0, 0.54)
        self._gate_rows(items, old_gate, new_gate, with_threshold=True, show_ba=False)
        if attempt == 1:
            self._text(items, "두 모델 모두 성능 기준을 충족하지 못했습니다.", 0, -0.40)
            self._text(items, "전극 및 EEG 신호 상태를 확인한 후 Calibration을 재측정합니다.", 0, -0.51)
            footer = "SPACE : 재측정 시작       ESC : 실험 종료"
        else:
            self._text(items, "두 차례의 Calibration에서 모두 성능 기준을 충족하지 못했습니다.", 0, -0.39)
            self._text(items, "실시간 뉴로피드백 대신 추가 운동 상상 EEG 데이터를 수집합니다.", 0, -0.50)
            self._text(items, "오프라인 측정: 총 30 Trial (LEFT 15 / RIGHT 15)", 0, -0.61)
            footer = "SPACE : 오프라인 측정 시작       ESC : 실험 종료"
        self._text(items, footer, 0, -0.81)
        self._show(items)

    def selection_success(self, attempt, old_gate, new_gate, selected_mode, threshold):
        items = []
        self._text(items, f"{attempt}차 Calibration — Quality Gate 통과", 0, 0.56)
        self._gate_rows(items, old_gate, new_gate, with_threshold=False, show_ba=True)
        self._text(items, f"최종 선택 모델: {selected_mode}", 0, -0.44)
        self._text(items, f"적용 Threshold: {float(threshold):.4f}", 0, -0.55)
        self._text(items, "선택된 모델을 이용하여 온라인 뉴로피드백 실험을 진행합니다.", 0, -0.66)
        self._text(items, "SPACE : 본 실험 시작       ESC : 실험 종료", 0, -0.82)
        self._show(items)

    def online_complete(self, results, selected_mode, threshold):
        items = []
        self._text(items, f"온라인 본 실험 {len(results)} Trial 완료", 0, 0.50)
        self._text(items, f"선택 모델: {selected_mode}   |   Threshold: {threshold:.4f}", 0, 0.36)
        # Two compact columns around screen center.
        label_x, value_x = -0.19, 0.23
        self._text(items, "평가 항목", label_x, 0.23)
        self._text(items, "결과", value_x, 0.23)
        n = len(results)
        correct = sum(int(r.get("is_correct", 0)) for r in results)
        n_success = sum(r.get("status") == "SUCCESS" for r in results)
        left = [r for r in results if r.get("target_direction") == "LEFT"]
        right = [r for r in results if r.get("target_direction") == "RIGHT"]
        left_correct = sum(int(r.get("is_correct", 0)) for r in left)
        right_correct = sum(int(r.get("is_correct", 0)) for r in right)
        mean_seconds = float(np.mean([float(r["decision_time_s"]) for r in results])) if results else 0.0
        def percentage(a, b):
            return f"{100 * a / b:.1f}%" if b else "측정 불가"
        table = [
            ("전체 정확도 (Accuracy)", f"{percentage(correct, n)} ({correct}/{n})"),
            ("LEFT Recall", f"{percentage(left_correct, len(left))} ({left_correct}/{len(left)})"),
            ("RIGHT Recall", f"{percentage(right_correct, len(right))} ({right_correct}/{len(right)})"),
            ("Level 4 도달률", f"{percentage(n_success, n)} ({n_success}/{n})"),
            ("평균 판정 시간", f"{mean_seconds:.1f}초"),
        ]
        for i, (name, value) in enumerate(table):
            y = 0.12 - i * 0.105
            self._text(items, name, label_x, y)
            self._text(items, value, value_x, y)
        self._text(items, "SPACE : 실험 종료", 0, -0.65)
        self._show(items)

    def offline_complete(self, n_trials, n_left, n_right):
        items = []
        self._text(items, "오프라인 EEG 데이터 수집 완료", 0, 0.45)
        label_x, value_x = -0.16, 0.16
        self._text(items, "측정 항목", label_x, 0.24)
        self._text(items, "결과", value_x, 0.24)
        for i, (name, value) in enumerate((
            ("전체 Trial", f"{n_trials}회"),
            ("LEFT", f"{n_left}회"),
            ("RIGHT", f"{n_right}회"),
            ("데이터 저장", "완료"),
        )):
            y = 0.12 - i * 0.11
            self._text(items, name, label_x, y)
            self._text(items, value, value_x, y)
        self._text(items, "SPACE : 실험 종료", 0, -0.55)
        self._show(items)

    def eeg_unusable(self):
        items = []
        self._text(items, "EEG 데이터 수집 오류", 0, 0.34)
        self._text(items, "정상적인 뇌파 측정을 진행할 수 없습니다.", 0, 0.17)
        self._text(items, "전극 및 EEG 장비의 연결 상태를 확인해 주세요.", 0, -0.03)
        self._text(items, "SPACE : 실험 종료", 0, -0.32)
        self._show(items)



# =============================================================================
# PsychoPy Dynamic Fading UI
# =============================================================================
class OnlineTestUI:
    """Dynamic Fading UI matching feedback_preview_auto_v5.

    - Pure white background
    - Level 0: centered dashed circular outline only
    - Levels 1-3: centered filled circle + fixed LEFT/RIGHT arrow
    - SUCCESS: green cue
    - FAIL: red cue
    - The circle remains fixed at screen center for every level/direction.
    """

    def __init__(self, win):
        self.win = win

        # UI colors (RGB 0-255), matched to feedback_preview_auto_v5.
        self.colors = {
            1: (191, 191, 191),  # Level 1
            2: (126, 126, 126),  # Level 2
            3: (0, 0, 0),        # Level 3
            "SUCCESS": (0, 175, 80),
            "FAIL": (191, 0, 0),
        }
        self.level0_dash_color = (140, 140, 140)
        self.black = (0, 0, 0)

        # Header positions use normalized screen coordinates so they remain
        # visible even on different monitor aspect ratios.
        # Trial counter: top-right.
        self.trial_text = visual.TextStim(
            win,
            text="",
            pos=(0.82, 0.35),
            height=0.06,
            color=self.black,
            colorSpace="rgb255",
            units="norm",
        )

        # Ground-truth cue: top-center.
        self.target_text = visual.TextStim(
            win,
            text="",
            pos=(0.0, 0.35),
            height=0.06,
            color=self.black,
            colorSpace="rgb255",
            units="norm",
        )

        # ---------------------------------------------------------------------
        # Filled cue used from Level 1 onward.
        # IMPORTANT: circle position is always fixed at (0, 0).
        # ---------------------------------------------------------------------
        initial_fill = self.colors[1]
        self.circle = visual.Circle(
            win,
            radius=CUE_RADIUS,
            edges=128,
            pos=(0, 0),
            fillColor=initial_fill,
            lineColor=initial_fill,  # same as fill -> no visible outline
            lineWidth=1,
            colorSpace="rgb255",
            units="height",
        )

        # ---------------------------------------------------------------------
        # Level 0: dashed outline circle, no fill and no arrow.
        # PsychoPy does not provide a robust dashed Circle across versions,
        # so each dash is drawn as a short open ShapeStim arc.
        # ---------------------------------------------------------------------
        self.level0_dashes = []
        radius = CUE_RADIUS
        n_dashes = 18
        dash_fraction = 0.58
        points_per_dash = 7

        for i in range(n_dashes):
            cell_start = 2.0 * math.pi * i / n_dashes
            cell_width = 2.0 * math.pi / n_dashes
            dash_width = cell_width * dash_fraction
            a0 = cell_start + 0.5 * (cell_width - dash_width)
            a1 = a0 + dash_width

            vertices = []
            for j in range(points_per_dash):
                a = a0 + (a1 - a0) * j / (points_per_dash - 1)
                vertices.append((radius * math.cos(a), radius * math.sin(a)))

            dash = visual.ShapeStim(
                win,
                vertices=vertices,
                closeShape=False,
                fillColor=None,
                lineColor=self.level0_dash_color,
                lineWidth=3,
                colorSpace="rgb255",
                units="height",
            )
            self.level0_dashes.append(dash)

        # Exactly the same arrow silhouettes as the original offline protocol4.
        # Draw the arrow first, then the centered circle over its junction.
        self.left_arrow = visual.ShapeStim(
            win,
            vertices=CUE_LEFT_ARROW_VERTICES,
            closeShape=True,
            pos=(0, 0),
            fillColor=initial_fill,
            lineColor=initial_fill,
            lineWidth=1,
            colorSpace="rgb255",
            units="height",
        )
        self.right_arrow = visual.ShapeStim(
            win,
            vertices=CUE_RIGHT_ARROW_VERTICES,
            closeShape=True,
            pos=(0, 0),
            fillColor=initial_fill,
            lineColor=initial_fill,
            lineWidth=1,
            colorSpace="rgb255",
            units="height",
        )

        self.info_ui = KoreanResultsUI(win)
        self.start_text = self.info_ui.initial_calibration()

        self.calibration_summary_text = visual.TextStim(
            win,
            text="",
            pos=(0, 0),
            height=0.036,
            color=self.black,
            colorSpace="rgb255",
            wrapWidth=1.7,
            units="height",
        )
        
        # 실험 시작 직후 5초 RELAX 안내 문구
        self.initial_relax_text = visual.TextStim(
            win,
            text="RELAX",
            pos=(0, 0),
            height=0.038,
            color=self.black,
            colorSpace="rgb255",
            wrapWidth=1.7,
            units="height",
        )

        # [추가] 10 Trial 휴식용 안내 문구
        self.block_rest_text = visual.TextStim(
            win,
            text="REST",
            pos=(0, 0),
            height=0.038,
            color=self.black,
            colorSpace="rgb255",
            wrapWidth=1.7,
            units="height",
        )

    def _set_cue_color(self, color):
        """Apply one color to the shared circle and both arrow shapes."""
        self.circle.fillColor = color
        self.circle.lineColor = color
        for arrow in (self.left_arrow, self.right_arrow):
            arrow.fillColor = color
            arrow.lineColor = color

    def _set_direction(self, direction: str):
        """Select the protocol4 arrow geometry without moving the centered circle."""
        direction = direction.upper()
        self.circle.pos = (0, 0)
        if direction == "LEFT":
            self.current_arrow = self.left_arrow
        elif direction == "RIGHT":
            self.current_arrow = self.right_arrow
        else:
            raise ValueError(f"Unknown direction: {direction!r}")

    def _draw_trial_number(self, trial_number: int, target_direction: str):
        self.trial_text.text = f"Trial {trial_number:02d}/{N_TRIALS}"
        self.target_text.text = str(target_direction).upper()
        self.trial_text.draw()
        self.target_text.draw()

    def _draw_level0_dashes(self):
        for dash in self.level0_dashes:
            dash.draw()

    def _draw_directional_cue(self, candidate: str, color):
        self._set_direction(candidate)
        self._set_cue_color(color)

        # Same as offline: arrow first, centered circle last.
        self.current_arrow.draw()
        self.circle.draw()

    def draw_feedback(
        self,
        trial_number: int,
        level: int,
        candidate: str | None,
        target_direction: str,
        status: str | None = None,
    ):
        self._draw_trial_number(trial_number, target_direction)

        # Level 0 is shared by LEFT/RIGHT: dashed circle only, no arrow.
        # Level 0 always shows the common neutral screen. According to the
        # paper's Dynamic Fading rule, the next classification at Level 0
        # becomes the new Candidate Decision.
        if status is None and int(level) == 0:
            self._draw_level0_dashes()
            return

        if candidate not in {"LEFT", "RIGHT"}:
            raise ValueError("A LEFT/RIGHT candidate is required when an arrow is shown.")

        if status is None:
            if int(level) not in {1, 2, 3}:
                raise ValueError(f"Unexpected active Selection Level: {level}")
            color = self.colors[int(level)]
        else:
            status = status.upper()
            if status not in {"SUCCESS", "FAIL"}:
                raise ValueError(f"Unknown status: {status!r}")
            color = self.colors[status]

        self._draw_directional_cue(candidate, color)

    def _draw_calibration_header(self, trial_number: int, target_direction: str | None = None):
        self.trial_text.text = f"Calibration {trial_number:02d}/{CALIBRATION_TRIALS}"
        self.target_text.text = "" if target_direction is None else str(target_direction).upper()
        self.trial_text.draw()
        if target_direction is not None:
            self.target_text.draw()

    def show_calibration_rest(self, trial_number, explore, global_clock, runtime):
        """1-s visual REST before calibration MI."""
        holder = {}

        def on_flip():
            holder["time"] = global_clock.getTime()
            holder["sample"] = runtime.mark_stream_sample()
            explore.set_marker(CALIBRATION_REST_ONSET)

        event.clearEvents(eventType="keyboard")
        # Calibration REST intentionally shows no text, trial number, target,
        # or arrow.  Only the same centered black circle used by the cue is
        # displayed so the visual transition between trials stays minimal.
        self.circle.pos = (0, 0)
        self._set_cue_color(self.black)
        self.circle.draw()
        self.win.callOnFlip(on_flip)
        self.win.flip()
        wait_with_escape(CALIBRATION_REST_DURATION)
        return holder["time"], holder["sample"]

    def begin_calibration_trial(
        self,
        trial_number,
        target_direction,
        explore,
        global_clock,
        runtime,
    ):
        """Show the instructed direction and mark the exact EEG sample at cue onset."""
        holder = {}
        target_direction = str(target_direction).upper()

        def on_flip():
            holder["time"] = global_clock.getTime()
            holder["sample"] = runtime.mark_stream_sample()
            marker = (
                CALIBRATION_LEFT_ONSET
                if target_direction == "LEFT"
                else CALIBRATION_RIGHT_ONSET
            )
            explore.set_marker(marker)

        # Calibration trial screen: cue only.
        # Do not draw trial number, LEFT/RIGHT text, or any other text.
        self._draw_directional_cue(target_direction, self.black)
        self.win.callOnFlip(on_flip)
        self.win.flip()
        return holder["time"], holder["sample"]

    def show_quality_failure(self, attempt, old_gate, new_gate):
        self.info_ui.quality_failure(attempt, old_gate, new_gate)

    def show_selection_success(self, attempt, old_gate, new_gate, selected_mode, threshold):
        self.info_ui.selection_success(attempt, old_gate, new_gate, selected_mode, threshold)

    def show_eeg_unusable(self):
        self.info_ui.eeg_unusable()

    def show_finetuning(self):
        """Keep a stable status screen visible while the CPU evaluates heads."""
        event.clearEvents(eventType="keyboard")
        self.calibration_summary_text.text = "모델 재학습 중 …"
        self.calibration_summary_text.draw()
        self.win.flip()
        check_escape()

    def show_calibration_block_rest(self, duration: float, explore):
        """Between calibration blocks, show only the REST text."""
        event.clearEvents(eventType="keyboard")
        # After Trial 10, display only the REST text during the block break.
        # No cue circle, arrow, trial number, or direction text is shown.
        self.block_rest_text.draw()
        self.win.callOnFlip(explore.set_marker, CALIBRATION_BLOCK_REST_ONSET)
        self.win.flip()
        wait_with_escape(duration)

    def show_trial_rest(self, trial_number, target_direction, explore, global_clock):
        """1-s REST: Level-0 dashed circle is visible; no classification occurs."""
        holder = {}

        def on_flip():
            holder["time"] = global_clock.getTime()
            explore.set_marker(TRIAL_REST_ONSET)

        event.clearEvents(eventType="keyboard")
        self.draw_feedback(trial_number, level=0, candidate=None, target_direction=target_direction)
        self.win.callOnFlip(on_flip)
        self.win.flip()
        wait_with_escape(TRIAL_REST_DURATION)
        return holder["time"]

    def begin_classification(self, trial_number, target_direction, explore, global_clock, runtime):
        """Keep Level 0 on screen and mark the exact start of the first 0.5-s window."""
        holder = {}

        def on_flip():
            holder["time"] = global_clock.getTime()
            holder["sample"] = runtime.mark_stream_sample()
            explore.set_marker(CLASSIFICATION_ONSET)
            explore.set_marker(LEVEL_0_ONSET)

        self.draw_feedback(trial_number, level=0, candidate=None, target_direction=target_direction)
        self.win.callOnFlip(on_flip)
        self.win.flip()
        return holder["time"], holder["sample"]

    def show_level(self, trial_number, level, candidate, target_direction, explore, global_clock):
        holder = {}

        def on_flip():
            holder["time"] = global_clock.getTime()
            explore.set_marker(level_marker(level))

        self.draw_feedback(trial_number, level=level, candidate=candidate, target_direction=target_direction)
        self.win.callOnFlip(on_flip)
        self.win.flip()
        return holder["time"]

    def show_outcome(self, trial_number, candidate, target_direction, status, explore, global_clock):
        holder = {}
        status = status.upper()
        if status == "SUCCESS":
            marker = SUCCESS_LEFT_ONSET if candidate == "LEFT" else SUCCESS_RIGHT_ONSET
        elif status == "FAIL":
            marker = FAIL_LEFT_ONSET if candidate == "LEFT" else FAIL_RIGHT_ONSET
        else:
            raise ValueError(f"Unknown status: {status!r}")

        def on_flip():
            holder["time"] = global_clock.getTime()
            explore.set_marker(marker)

        self.draw_feedback(
            trial_number,
            level=4 if status == "SUCCESS" else 0,
            candidate=candidate,
            target_direction=target_direction,
            status=status,
        )
        self.win.callOnFlip(on_flip)
        self.win.flip()
        wait_with_escape(RESULT_DISPLAY_DURATION)
        return holder["time"]

    def show_final_results(self, results, selected_mode, threshold):
        # Accuracy and direction recalls use final Trial judgments (FAIL = incorrect).
        # Level 4 success is displayed separately; it does not imply a correct label.
        self.info_ui.online_complete(results, selected_mode, threshold)

    def show_initial_relax(self, duration: float, explore):
        """Show the initial RELAX screen before the calibration block."""
        event.clearEvents(eventType="keyboard")
        self.initial_relax_text.draw()
        self.win.callOnFlip(explore.set_marker, INITIAL_RELAX_ONSET)
        self.win.flip()
        wait_with_escape(duration)

    def show_main_relax(self, duration: float, explore):
        """Show a RELAX screen immediately before the 30-trial main experiment."""
        event.clearEvents(eventType="keyboard")
        self.initial_relax_text.draw()
        self.win.callOnFlip(explore.set_marker, MAIN_RELAX_ONSET)
        self.win.flip()
        wait_with_escape(duration)

        # [추가] 5초 휴식 화면 노출
    def show_block_rest(self, duration: float, explore):
        """Show the between-block REST screen and mark its visual onset."""
        event.clearEvents(eventType="keyboard")
        self.block_rest_text.draw()
        self.win.callOnFlip(explore.set_marker, BLOCK_REST_ONSET)
        self.win.flip()
        wait_with_escape(duration)


# =============================================================================
# Protocol4-based 30-trial offline motor-imagery fallback
# =============================================================================
class OfflineProtocolUI:
    """Protocol4 fixation / arrow+circle cue / circle-only MI / blank rest."""
    def __init__(self, win):
        self.win = win
        self.info_ui = KoreanResultsUI(win)
        black = (0, 0, 0)
        def rect(width, height):
            return visual.Rect(win, width=width, height=height, pos=(0, 0),
                               fillColor=black, lineColor=black,
                               colorSpace="rgb255", units="height")
        self.fixation = [rect(0.07, 0.010), rect(0.010, 0.07)]
        self.circle = visual.Circle(win, radius=CUE_RADIUS, edges=128, pos=(0, 0),
                                    fillColor=black, lineColor=black,
                                    colorSpace="rgb255", units="height")
        self.left_arrow = visual.ShapeStim(
            win, vertices=CUE_LEFT_ARROW_VERTICES,
            closeShape=True, fillColor=black, lineColor=black,
            colorSpace="rgb255", units="height")
        self.right_arrow = visual.ShapeStim(
            win, vertices=CUE_RIGHT_ARROW_VERTICES,
            closeShape=True, fillColor=black, lineColor=black,
            colorSpace="rgb255", units="height")
        self.relax = visual.TextStim(win, text="RELAX", height=0.038, pos=(0, 0), color=black,
                                     colorSpace="rgb255", units="height")
    def show_stage(self, stimuli, duration, marker, explore, global_clock, runtime):
        holder = {}
        def onset():
            holder["time"] = global_clock.getTime()
            holder["sample"] = runtime.mark_stream_sample()
            explore.set_marker(marker)
        if stimuli is not None:
            if not isinstance(stimuli, (list, tuple)):
                stimuli = [stimuli]
            for stimulus in stimuli:
                stimulus.draw()
        self.win.callOnFlip(onset)
        self.win.flip()
        wait_with_escape(duration)
        return holder


def run_offline_30_trials(win, explore, runtime, clock, writer, schedule, subject, offline_file=None):
    # Same white background used by Calibration and Online Dynamic Fading.
    win.color = (255, 255, 255)
    ui = OfflineProtocolUI(win)
    # The 2nd Quality Gate result screen has already received SPACE confirmation.
    explore.set_marker(OFFLINE_START)
    ui.show_stage(ui.relax, OFFLINE_RELAX_DURATION, OFFLINE_RELAX_ONSET,
                  explore, clock, runtime)
    # Protocol4 has a 1-s beep and 1-s post-beep rest. Hardware-specific audio
    # output may be unavailable; do not abort EEG collection solely for a beep.
    try:
        from psychopy import sound
        tone = sound.Sound(value=1000, secs=1.0, stereo=True)
        tone.play()
    except Exception as exc:
        print(f"Offline start beep unavailable: {exc}")
    wait_with_escape(2.0)
    for trial, direction in enumerate(schedule, 1):
        cue_arrow = ui.left_arrow if direction == "LEFT" else ui.right_arrow
        cue_marker = OFFLINE_CUE_LEFT_ONSET if direction == "LEFT" else OFFLINE_CUE_RIGHT_ONSET
        mi_marker = OFFLINE_MI_LEFT_ONSET if direction == "LEFT" else OFFLINE_MI_RIGHT_ONSET
        fixation = ui.show_stage(ui.fixation, OFFLINE_FIXATION_DURATION,
                                 OFFLINE_FIXATION_ONSET, explore, clock, runtime)
        cue = ui.show_stage([cue_arrow, ui.circle], OFFLINE_CUE_DURATION,
                            cue_marker, explore, clock, runtime)
        mi = ui.show_stage(ui.circle, OFFLINE_MI_DURATION,
                           mi_marker, explore, clock, runtime)
        rest = ui.show_stage(None, OFFLINE_REST_DURATION,
                             OFFLINE_REST_ONSET, explore, clock, runtime)
        writer.writerow({
            "subject": subject, "trial": trial, "target_direction": direction,
            "fixation_marker": OFFLINE_FIXATION_ONSET, "cue_marker": cue_marker,
            "mi_marker": mi_marker, "rest_marker": OFFLINE_REST_ONSET,
            "fixation_onset_s": f"{fixation['time']:.6f}",
            "cue_onset_s": f"{cue['time']:.6f}",
            "mi_onset_s": f"{mi['time']:.6f}",
            "rest_onset_s": f"{rest['time']:.6f}",
            "fixation_sample": fixation["sample"], "cue_sample": cue["sample"],
            "mi_sample": mi["sample"], "rest_sample": rest["sample"],
            "trial_end_s": f"{clock.getTime():.6f}",
            "experiment_mode": "OFFLINE_FALLBACK",
            "reason": "TWO_QUALITY_GATES_FAILED",
        })
        print(f"Offline {trial:02d}/{N_TRIALS} | target={direction}")
    explore.set_marker(OFFLINE_END)
    # Ensure the file has been written before displaying "데이터 저장: 완료".
    if offline_file is not None:
        offline_file.flush()
    n_left = sum(direction == "LEFT" for direction in schedule)
    n_right = sum(direction == "RIGHT" for direction in schedule)
    ui.info_ui.offline_complete(len(schedule), n_left, n_right)


# =============================================================================
# Complete adaptive experiment
# =============================================================================
def main():
    args = parse_arguments()
    subject = args.subject.strip().lower()
    model_path, bundle = load_bundle(subject, args.model_file, args.model_dir)
    runtime = BundleRuntime(bundle)
    # PRE-FLIGHT: missing training features must fail before EEG connection/recording.
    x_off, y_off, id_off = load_offline_training_data(args, runtime, bundle, model_path)
    offline_threshold = _extract_offline_threshold(bundle)
    if not np.isfinite(offline_threshold) or not (0.0 <= offline_threshold <= 1.0):
        raise ValueError(f"Invalid frozen OLD offline threshold: {offline_threshold}")
    window_samples = int(round(CLASSIFICATION_WINDOW * runtime.fs))
    calibration_seed = None if args.seed is None else args.seed + 100003
    main_schedule = make_balanced_target_schedule(N_TRIALS, BLOCK_REST_INTERVAL, seed=args.seed)
    offline_schedule = make_balanced_target_schedule(N_TRIALS, N_TRIALS,
                                                     seed=None if args.seed is None else args.seed + 300003)
    output = build_output_paths(args)
    (output_dir, eeg_base, online_path, cal_log_path, cal_summary_path,
     offline_path, decision_path) = output
    for filename in output[2:]:
        if filename.exists():
            raise FileExistsError(f"{filename} exists; use a new -f name or --timestamp")

    print("=" * 80)
    print("Adaptive MI-BCI: 20-trial calibration -> OLD/NEW-A gate -> 30 trials")
    print(f"Participant     : {subject}")
    print(f"Model           : {model_path}")
    print(f"Frozen features : {runtime.pipeline_summary()}")
    print(f"Channels        : {runtime.selected_channels}")
    print(f"Offline features: {x_off.shape}, trials={len(np.unique(id_off))}")
    print(f"LDA weights     : offline={OFFLINE_TRAIN_WEIGHT}, today={DAILY_TRAIN_WEIGHT}")
    print(f"Thresholds      : OLD={offline_threshold:.6f}, NEW-A={NEW_THRESHOLD:.4f}")
    print("Fallback        : one repeat calibration, then offline 30 trials")
    print("=" * 80)

    win = visual.Window(size=(3440, 1440), fullscr=not args.windowed, screen=args.screen,
                        units="height", color=(255, 255, 255),
                        colorSpace="rgb255", allowGUI=args.windowed)
    ui = OnlineTestUI(win)
    explore = Explore()
    connected = recording = subscribed = False
    clock = core.Clock()
    results = []
    attempt_results = []
    selected_mode = None
    mode = "NOT_STARTED"
    final_status = "ABORTED_OR_ERROR"
    decision_record_written = False

    calibration_fields = [
        "subject", "attempt", "trial", "target_direction", "old_probability_sequence",
        "old_trial_median_probability", "new_oof_probability_sequence",
        "new_oof_trial_median_probability", "calibration_rest_onset_s",
        "calibration_rest_stream_sample", "calibration_cue_onset_s",
        "calibration_cue_stream_sample", "eeg_qc_passed", "eeg_qc_reason",
    ]
    summary_fields = ["subject", "attempt", "model", "threshold", "auc", "delta_p",
                      "left_recall", "right_recall", "ba", "accuracy", "passed",
                      "eeg_qc_passed", "eeg_qc_reason", "selected_model"]
    online_fields = [
        "subject", "trial", "block", "model_mode", "target_direction",
        "threshold_used", "threshold_source", "offline_threshold", "new_threshold",
        "prediction_sequence", "predicted_label_sequence", "right_probability_sequence",
        "shadow_probability_sequence", "shadow_prediction_sequence", "shadow_model",
        "selection_level_sequence", "candidate_sequence", "initial_candidate_decision",
        "candidate_decision", "final_decision", "is_correct", "final_selection_level",
        "n_predictions", "decision_time_s", "actual_wall_time_s", "status",
        "trial_rest_onset_s", "classification_onset_s",
        "classification_onset_stream_sample", "outcome_onset_s", "experiment_mode",
    ]
    offline_fields = [
        "subject", "trial", "target_direction", "fixation_marker", "cue_marker", "mi_marker",
        "rest_marker", "fixation_onset_s", "cue_onset_s", "mi_onset_s", "rest_onset_s",
        "fixation_sample", "cue_sample", "mi_sample", "rest_sample", "trial_end_s",
        "experiment_mode", "reason",
    ]
    decision_fields = ["subject", "attempts", "selected_model", "experiment_mode",
                       "status", "reason", "old_auc", "old_delta_p", "old_ba", "old_passed",
                       "new_auc", "new_delta_p", "new_ba", "new_passed", "eeg_qc_passed"]

    try:
        runtime.reset()
        explore.connect(device_name=args.device_name)
        connected = True
        explore.stream_processor.subscribe(callback=runtime.process_packet, topic=TOPICS.raw_ExG)
        subscribed = True
        explore.record_data(file_name=str(eeg_base), file_type="csv", do_overwrite=False)
        recording = True
        stream_ready_deadline = time.monotonic() + 3.0
        while runtime.sample_count == 0 and time.monotonic() < stream_ready_deadline:
            check_escape()
            core.wait(0.02)
        if runtime.sample_count == 0:
            raise RuntimeError("No live ExG packets from Explore device")

        with (cal_log_path.open("x", newline="", encoding="utf-8-sig") as cal_file,
              cal_summary_path.open("x", newline="", encoding="utf-8-sig") as summary_file,
              online_path.open("x", newline="", encoding="utf-8-sig") as online_file,
              offline_path.open("x", newline="", encoding="utf-8-sig") as offline_file,
              decision_path.open("x", newline="", encoding="utf-8-sig") as decision_file):
            cal_writer = csv.DictWriter(cal_file, fieldnames=calibration_fields)
            summary_writer = csv.DictWriter(summary_file, fieldnames=summary_fields)
            online_writer = csv.DictWriter(online_file, fieldnames=online_fields)
            offline_writer = csv.DictWriter(offline_file, fieldnames=offline_fields)
            decision_writer = csv.DictWriter(decision_file, fieldnames=decision_fields)
            for writer in (cal_writer, summary_writer, online_writer, offline_writer, decision_writer):
                writer.writeheader()

            wait_for_space(ui.start_text, win)
            clock.reset()
            explore.set_marker(SESSION_START)
            ui.show_initial_relax(INITIAL_RELAX_DURATION, explore)

            final_cal = None
            for attempt in range(1, MAX_CALIBRATION_ATTEMPTS + 1):
                mode = f"CALIBRATION_{attempt}"
                if attempt == 2:
                    # The retry is never performed without SPACE confirmation.
                    previous = attempt_results[-1]
                    ui.show_quality_failure(1, previous["old"], previous["new"])
                    explore.set_marker(CALIBRATION_RETRY_START)

                schedule = make_balanced_target_schedule(
                    CALIBRATION_TRIALS, CALIBRATION_BLOCK_SIZE,
                    seed=None if calibration_seed is None else calibration_seed + attempt - 1)
                explore.set_marker(CALIBRATION_START)
                epochs, labels, trial_ids, trial_meta = [], [], [], []
                for trial in range(1, CALIBRATION_TRIALS + 1):
                    direction = schedule[trial - 1]
                    rest_time, rest_sample = ui.show_calibration_rest(trial, explore, clock, runtime)
                    cue_time, start_sample = ui.begin_calibration_trial(
                        trial, direction, explore, clock, runtime)
                    label = (runtime.output_spec["right_label"] if direction == "RIGHT"
                             else runtime.output_spec["left_label"])
                    for j in range(CALIBRATION_WINDOWS_PER_TRIAL):
                        epoch = runtime.get_window_epoch(start_sample + j * window_samples,
                                                         window_samples, timeout=2.0)
                        epochs.append(np.array(epoch, copy=True))
                        labels.append(label)
                        trial_ids.append(trial)
                    trial_meta.append({
                        "trial": trial, "target_direction": direction,
                        "rest_time": rest_time, "rest_sample": rest_sample,
                        "cue_time": cue_time, "cue_sample": start_sample,
                    })
                    print(f"Calibration {attempt} trial {trial:02d}/20 {direction}")
                    if trial % CALIBRATION_BLOCK_SIZE == 0 and trial < CALIBRATION_TRIALS:
                        ui.show_calibration_block_rest(CALIBRATION_BLOCK_REST_DURATION, explore)
                explore.set_marker(CALIBRATION_END)
                if attempt == 2:
                    explore.set_marker(CALIBRATION_RETRY_END)

                x_cal = np.concatenate(epochs, axis=0)
                y_cal = np.asarray(labels)
                tid_cal = np.asarray(trial_ids, dtype=int)
                qc = basic_eeg_qc(x_cal)
                if not qc["passed"]:
                    print(f"EEG QC failed: {qc['reason']}")
                    # Even when flatline is detected, record attempt and retry once.
                    # Do not train/score an invalid epoch set.
                    old_gate = new_gate = {
                        "threshold": float("nan"), "auc": float("nan"),
                        "delta_p": float("nan"), "left_recall": float("nan"),
                        "right_recall": float("nan"), "ba": float("nan"),
                        "accuracy": float("nan"), "passed": False,
                    }
                    old_prob = new_prob = np.full(len(y_cal), np.nan)
                else:
                    x_features = runtime.extract_frozen_features(x_cal)
                    if x_features.shape != (len(y_cal), x_off.shape[1]) or not np.isfinite(x_features).all():
                        raise ValueError("Frozen feature dimensions mismatch with offline training cache")
                    old_prob = runtime.right_probabilities_from_features(runtime.old_classifier, x_features)
                    ui.show_finetuning()
                    new_prob = build_new_classifier_and_oof(runtime, x_off, y_off, id_off,
                                                             x_features, y_cal, tid_cal,
                                                             calibration_seed)
                    y_trials, p_old_trial = aggregate_trial_probabilities(
                        y_cal, tid_cal, old_prob, runtime.output_spec["right_label"])
                    _, p_new_trial = aggregate_trial_probabilities(
                        y_cal, tid_cal, new_prob, runtime.output_spec["right_label"])
                    old_gate = trial_gate_metrics(y_trials, p_old_trial, offline_threshold)
                    new_gate = trial_gate_metrics(y_trials, p_new_trial, NEW_THRESHOLD)

                selected_mode = (choose_model(old_gate, new_gate) if qc["passed"] else None)
                attempt_results.append({"attempt": attempt, "old": old_gate,
                                        "new": new_gate, "qc": qc, "selected": selected_mode})
                for meta in trial_meta:
                    idx = tid_cal == meta["trial"]
                    cal_writer.writerow({
                        "subject": subject, "attempt": attempt, "trial": meta["trial"],
                        "target_direction": meta["target_direction"],
                        "old_probability_sequence": _csv_float_sequence(old_prob[idx]),
                        "old_trial_median_probability": f"{float(np.median(old_prob[idx])):.8f}",
                        "new_oof_probability_sequence": _csv_float_sequence(new_prob[idx]),
                        "new_oof_trial_median_probability": f"{float(np.median(new_prob[idx])):.8f}",
                        "calibration_rest_onset_s": f"{meta['rest_time']:.6f}",
                        "calibration_rest_stream_sample": meta["rest_sample"],
                        "calibration_cue_onset_s": f"{meta['cue_time']:.6f}",
                        "calibration_cue_stream_sample": meta["cue_sample"],
                        "eeg_qc_passed": int(qc["passed"]), "eeg_qc_reason": qc["reason"],
                    })
                cal_file.flush()
                for model_name, gate in (("OLD", old_gate), ("NEW-A", new_gate)):
                    summary_writer.writerow({
                        "subject": subject, "attempt": attempt, "model": model_name,
                        "eeg_qc_passed": int(qc["passed"]), "eeg_qc_reason": qc["reason"],
                        "selected_model": selected_mode or "NONE",
                        **gate,
                    })
                summary_file.flush()
                print(f"Attempt {attempt}: EEG QC={qc['passed']}, "
                      f"OLD BA={old_gate['ba']:.3f} passed={old_gate['passed']}, "
                      f"NEW-A BA={new_gate['ba']:.3f} passed={new_gate['passed']}, "
                      f"chosen={selected_mode or 'NONE'}")
                if selected_mode:
                    final_cal = (x_features, y_cal, tid_cal)
                    break

            attempts = len(attempt_results)
            last = attempt_results[-1]
            if not selected_mode:
                if not last["qc"]["passed"]:
                    mode = "EEG_UNUSABLE"
                    final_status = "STOPPED_BAD_EEG"
                    ui.show_eeg_unusable()
                else:
                    mode = "OFFLINE_FALLBACK"
                    ui.show_quality_failure(2, last["old"], last["new"])
                    run_offline_30_trials(win, explore, runtime, clock, offline_writer,
                                          offline_schedule, subject, offline_file)
                    offline_file.flush()
                    final_status = "COMPLETED_OFFLINE_30"
            else:
                mode = "ONLINE_DYNAMIC_FADING"
                x_features, y_cal, tid_cal = final_cal
                # Train the final NEW-A after model selection, using all 20 daily trials.
                # The OLD classifier remains fitted and unchanged.
                new_final = fit_new_a(runtime, x_off, y_off, id_off,
                                      x_features, y_cal, tid_cal)
                active = runtime.old_classifier if selected_mode == "OLD" else new_final
                shadow = new_final if selected_mode == "OLD" else runtime.old_classifier
                threshold = offline_threshold if selected_mode == "OLD" else NEW_THRESHOLD
                shadow_threshold = NEW_THRESHOLD if selected_mode == "OLD" else offline_threshold
                shadow_name = "NEW-A" if selected_mode == "OLD" else "OLD"
                ui.show_selection_success(attempts, last["old"], last["new"],
                                          selected_mode, threshold)
                ui.show_main_relax(MAIN_RELAX_DURATION, explore)
                explore.set_marker(MAIN_EXPERIMENT_START)
                for trial in range(1, N_TRIALS + 1):
                    direction = main_schedule[trial - 1]
                    block = (trial - 1) // BLOCK_REST_INTERVAL + 1
                    rest_onset = ui.show_trial_rest(trial, direction, explore, clock)
                    onset, start_sample = ui.begin_classification(trial, direction, explore, clock, runtime)
                    candidate = None
                    level = 0
                    final_direction = None
                    status = None
                    seq, prob_seq, shadow_seq, shadow_labels = [], [], [], []
                    label_seq, level_seq, candidates = [], [], []
                    initial_candidate = None
                    outcome_onset = None
                    decision_time = None
                    actual_wall_time = None
                    for j in range(1, MAX_PREDICTIONS + 1):
                        epoch = runtime.get_window_epoch(start_sample + (j - 1) * window_samples,
                                                         window_samples, timeout=2.0)
                        # Shared frozen features are extracted ONCE for both models.
                        features = runtime.extract_frozen_features(epoch)
                        p_selected = float(runtime.right_probabilities_from_features(active, features)[0])
                        p_shadow = float(runtime.right_probabilities_from_features(shadow, features)[0])
                        prediction = "RIGHT" if p_selected >= threshold else "LEFT"
                        shadow_prediction = "RIGHT" if p_shadow >= shadow_threshold else "LEFT"
                        explore.set_marker(PRED_RIGHT_ONSET if prediction == "RIGHT" else PRED_LEFT_ONSET)
                        seq.append("R" if prediction == "RIGHT" else "L")
                        label_seq.append(str(runtime.output_spec["right_label"] if prediction == "RIGHT"
                                             else runtime.output_spec["left_label"]))
                        prob_seq.append(f"{p_selected:.8f}")
                        shadow_seq.append(f"{p_shadow:.8f}")
                        shadow_labels.append("R" if shadow_prediction == "RIGHT" else "L")
                        if level == 0:
                            candidate = prediction
                            initial_candidate = initial_candidate or candidate
                            level = 1
                        elif prediction == candidate:
                            level = min(4, level + 1)
                        else:
                            level = max(0, level - 1)
                        level_seq.append(str(level))
                        candidates.append(candidate or "")
                        decision_time = j * CLASSIFICATION_WINDOW
                        actual_wall_time = clock.getTime() - onset
                        if level == 4:
                            status = "SUCCESS"
                            final_direction = candidate
                            outcome_onset = ui.show_outcome(
                                trial, candidate, direction, status, explore, clock)
                            break
                        ui.show_level(trial, level, candidate, direction, explore, clock)
                    if status is None:
                        status = "FAIL"
                        final_direction = None
                        decision_time = MAX_CLASSIFICATION_DURATION
                        actual_wall_time = clock.getTime() - onset
                        outcome_onset = ui.show_outcome(
                            trial, candidate, direction, status, explore, clock)
                    correct = int(final_direction == direction) if final_direction else 0
                    row = {
                        "subject": subject, "trial": trial, "block": block,
                        "model_mode": selected_mode, "target_direction": direction,
                        "threshold_used": f"{threshold:.8f}", "threshold_source": "offline" if selected_mode == "OLD" else "fixed_0.5",
                        "offline_threshold": f"{offline_threshold:.8f}",
                        "new_threshold": f"{NEW_THRESHOLD:.8f}",
                        "prediction_sequence": ",".join(seq),
                        "predicted_label_sequence": ",".join(label_seq),
                        "right_probability_sequence": ",".join(prob_seq),
                        "shadow_probability_sequence": ",".join(shadow_seq),
                        "shadow_prediction_sequence": ",".join(shadow_labels),
                        "shadow_model": shadow_name,
                        "selection_level_sequence": ",".join(level_seq),
                        "candidate_sequence": ",".join(candidates),
                        "initial_candidate_decision": initial_candidate or "",
                        "candidate_decision": candidate or "",
                        "final_decision": final_direction or "",
                        "is_correct": correct, "final_selection_level": int(level),
                        "n_predictions": len(seq), "decision_time_s": f"{decision_time:.3f}",
                        "actual_wall_time_s": f"{actual_wall_time:.6f}",
                        "status": status, "trial_rest_onset_s": f"{rest_onset:.6f}",
                        "classification_onset_s": f"{onset:.6f}",
                        "classification_onset_stream_sample": int(start_sample),
                        "outcome_onset_s": f"{outcome_onset:.6f}",
                        "experiment_mode": mode,
                    }
                    results.append(row)
                    online_writer.writerow(row)
                    online_file.flush()
                    print(f"Online {trial:02d}/{N_TRIALS} {selected_mode} "
                          f"target={direction} final={final_direction or 'NONE'} "
                          f"level={level} correct={correct}")
                    if trial % BLOCK_REST_INTERVAL == 0 and trial < N_TRIALS:
                        ui.show_block_rest(BLOCK_REST_DURATION, explore)
                final_status = "COMPLETED_ONLINE_30"
                ui.show_final_results(results, selected_mode, threshold)

            explore.set_marker(SESSION_END)
            decision_writer.writerow({
                "subject": subject, "attempts": attempts,
                "selected_model": selected_mode or "NONE", "experiment_mode": mode,
                "status": final_status, "reason": last["qc"]["reason"] if not last["qc"]["passed"]
                          else ("PASS" if selected_mode else "TWO_QUALITY_GATES_FAILED"),
                "old_auc": last["old"]["auc"], "old_delta_p": last["old"]["delta_p"],
                "old_ba": last["old"]["ba"], "old_passed": last["old"]["passed"],
                "new_auc": last["new"]["auc"], "new_delta_p": last["new"]["delta_p"],
                "new_ba": last["new"]["ba"], "new_passed": last["new"]["passed"],
                "eeg_qc_passed": last["qc"]["passed"],
            })
            decision_file.flush()
            decision_record_written = True

    except ExperimentAbort:
        final_status = "ABORTED_ESC"
        if connected:
            try:
                explore.set_marker(EXPERIMENT_ABORTED)
            except Exception:
                pass
        print("Experiment aborted using ESC")
    finally:
        # Preserve aborted/error session metadata even if no branch completed.
        if decision_path.exists() and not decision_record_written:
            try:
                last = attempt_results[-1] if attempt_results else None
                row = {
                    "subject": subject, "attempts": len(attempt_results),
                    "selected_model": selected_mode or "NONE", "experiment_mode": mode,
                    "status": final_status, "reason": "ABORT_OR_RUNTIME_ERROR",
                    "old_auc": last["old"]["auc"] if last else "",
                    "old_delta_p": last["old"]["delta_p"] if last else "",
                    "old_ba": last["old"]["ba"] if last else "",
                    "old_passed": last["old"]["passed"] if last else "",
                    "new_auc": last["new"]["auc"] if last else "",
                    "new_delta_p": last["new"]["delta_p"] if last else "",
                    "new_ba": last["new"]["ba"] if last else "",
                    "new_passed": last["new"]["passed"] if last else "",
                    "eeg_qc_passed": last["qc"]["passed"] if last else "",
                }
                write_header = decision_path.stat().st_size == 0
                with decision_path.open("a", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=decision_fields)
                    if write_header:
                        writer.writeheader()
                    writer.writerow(row)
            except Exception as exc:
                print(f"Could not write final experiment status: {exc}")
        if subscribed and connected:
            try:
                explore.stream_processor.unsubscribe(callback=runtime.process_packet, topic=TOPICS.raw_ExG)
            except Exception as exc:
                print(f"EEG unsubscribe failed: {exc}")
        if recording:
            try:
                explore.stop_recording()
            except Exception as exc:
                print(f"Stop recording failed: {exc}")
        if connected:
            try:
                explore.disconnect()
            except Exception as exc:
                print(f"Explore disconnect failed: {exc}")
        win.close()
        print(f"Status={final_status}, mode={mode}, output={output_dir}")
    core.quit()


if __name__ == "__main__":
    main()
