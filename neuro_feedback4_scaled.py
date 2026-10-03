from __future__ import annotations

import argparse
import csv
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
from sklearn.base import clone
from sklearn.metrics import balanced_accuracy_score, f1_score, roc_auc_score
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
SESSION_END = 99
EXPERIMENT_ABORTED = 98


# =============================================================================
# Experiment design
# =============================================================================
N_TRIALS = 40
CALIBRATION_TRIALS = 20
CALIBRATION_BLOCK_SIZE = 10
CALIBRATION_MI_DURATION = 3.0
CALIBRATION_REST_DURATION = 1.0
CALIBRATION_BLOCK_REST_DURATION = 5.0

CLASSIFICATION_WINDOW = 0.5
CALIBRATION_WINDOWS_PER_TRIAL = int(round(CALIBRATION_MI_DURATION / CLASSIFICATION_WINDOW))  # 6
CALIBRATION_OOF_FOLDS = 5

ORIGINAL_THRESHOLD_WEIGHT = 0.40
CALIBRATION_THRESHOLD_WEIGHT = 0.60

INITIAL_RELAX_DURATION = 5.0
MAIN_RELAX_DURATION = 5.0
TRIAL_REST_DURATION = 1.0
BLOCK_REST_INTERVAL = 10
BLOCK_REST_DURATION = 5.0
MAIN_MODEL_ORDER = ["NEW", "OLD", "NEW", "OLD"]
MAX_CLASSIFICATION_DURATION = 15.0
MAX_PREDICTIONS = int(MAX_CLASSIFICATION_DURATION / CLASSIFICATION_WINDOW)  # 30
RESULT_DISPLAY_DURATION = 1.0
FINAL_RESULT_DURATION = 5.0



class ExperimentAbort(Exception):
    """Raised when Escape is pressed."""


# =============================================================================
# Command-line arguments
# =============================================================================
def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Team-generic New/Old block-alternating Dynamic Fading MI BCI test. "
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
# Threshold helpers
# =============================================================================
def threshold_metrics(y_true: np.ndarray, prob_right: np.ndarray, threshold: float) -> dict:
    y_true = np.asarray(y_true, dtype=int)
    prob_right = np.asarray(prob_right, dtype=float)
    pred = (prob_right >= float(threshold)).astype(int)
    return {
        "threshold": float(threshold),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, pred)),
        "f1_right": float(f1_score(y_true, pred, pos_label=1, zero_division=0)),
        "accuracy": float(np.mean(pred == y_true)),
    }


def find_best_balanced_threshold(
    y_true: np.ndarray,
    prob_right: np.ndarray,
    reference_threshold: float,
) -> tuple[float, dict]:
    """Maximize balanced accuracy; ties go to the reference threshold."""
    y_true = np.asarray(y_true, dtype=int)
    prob_right = np.asarray(prob_right, dtype=float)
    if set(np.unique(y_true)) != {0, 1}:
        raise ValueError("Both LEFT and RIGHT are required for threshold optimization.")
    if not np.isfinite(prob_right).all():
        raise ValueError("P(RIGHT) contains NaN/Inf.")

    unique_scores = np.unique(prob_right)
    midpoints = (unique_scores[:-1] + unique_scores[1:]) / 2.0
    candidates = np.unique(
        np.clip(
            np.concatenate([
                np.asarray([0.0, 1.0, float(reference_threshold)]),
                midpoints,
            ]),
            0.0,
            1.0,
        )
    )

    best_threshold = float(reference_threshold)
    best_metrics = threshold_metrics(y_true, prob_right, best_threshold)
    best_distance = 0.0
    for threshold in candidates:
        metrics = threshold_metrics(y_true, prob_right, float(threshold))
        distance = abs(float(threshold) - float(reference_threshold))
        if (
            metrics["balanced_accuracy"] > best_metrics["balanced_accuracy"] + 1e-12
            or (
                abs(metrics["balanced_accuracy"] - best_metrics["balanced_accuracy"]) <= 1e-12
                and distance < best_distance - 1e-12
            )
        ):
            best_threshold = float(threshold)
            best_metrics = metrics
            best_distance = distance
    return best_threshold, best_metrics


def choose_between_thresholds(
    y_true: np.ndarray,
    prob_right: np.ndarray,
    threshold_a: float,
    source_a: str,
    threshold_b: float,
    source_b: str,
) -> dict:
    """Choose higher calibration BA; exact ties prefer A (the simpler/reference choice)."""
    metrics_a = threshold_metrics(y_true, prob_right, threshold_a)
    metrics_b = threshold_metrics(y_true, prob_right, threshold_b)
    if metrics_b["balanced_accuracy"] > metrics_a["balanced_accuracy"] + 1e-12:
        return {"threshold": float(threshold_b), "source": source_b, "metrics": metrics_b,
                "candidate_a": metrics_a, "candidate_b": metrics_b}
    return {"threshold": float(threshold_a), "source": source_a, "metrics": metrics_a,
            "candidate_a": metrics_a, "candidate_b": metrics_b}


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
        if arr.shape[0] == n_expected and arr.shape[1] != n_expected:
            arr = arr.T
        elif arr.shape[1] == n_expected:
            pass
        elif arr.shape[0] <= 32 and arr.shape[1] > arr.shape[0]:
            arr = arr.T
        if arr.shape[1] < n_expected:
            raise ValueError(f"Bundle expects {n_expected} channels, incoming packet is {arr.shape}.")
        arr = arr[:, :n_expected]
        if not np.isfinite(arr).all():
            raise ValueError("Incoming EEG contains NaN/Inf.")
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

    def clone_classifier_head(self):
        return clone(self.old_classifier)

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
# Calibration: New classifier + New/Old threshold selection
# =============================================================================
def build_new_classifier_and_oof(
    runtime: BundleRuntime,
    features: np.ndarray,
    model_labels: np.ndarray,
    trial_ids: np.ndarray,
    seed: int | None,
) -> tuple[object, np.ndarray]:
    """5-fold trial-grouped OOF; classifier labels may be any participant labels."""
    model_labels = np.asarray(model_labels)
    trial_ids = np.asarray(trial_ids, dtype=int)
    unique_trials = np.unique(trial_ids)
    right_label = runtime.output_spec["right_label"]

    trial_model_labels = np.asarray([model_labels[trial_ids == tid][0] for tid in unique_trials])
    for tid, label in zip(unique_trials, trial_model_labels):
        if not np.all(model_labels[trial_ids == tid] == label):
            raise RuntimeError(f"Calibration trial {tid} contains mixed labels.")
    trial_binary_labels = (trial_model_labels == right_label).astype(int)

    cv_seed = 20261003 if seed is None else int(seed)
    splitter = StratifiedKFold(
        n_splits=CALIBRATION_OOF_FOLDS,
        shuffle=True,
        random_state=cv_seed,
    )
    oof = np.full(len(model_labels), np.nan, dtype=np.float64)

    for train_trial_idx, test_trial_idx in splitter.split(unique_trials, trial_binary_labels):
        train_trials = unique_trials[train_trial_idx]
        test_trials = unique_trials[test_trial_idx]
        train_mask = np.isin(trial_ids, train_trials)
        test_mask = np.isin(trial_ids, test_trials)
        head = runtime.clone_classifier_head()
        head.fit(features[train_mask], model_labels[train_mask])
        oof[test_mask] = runtime.right_probabilities_from_features(head, features[test_mask])

    if not np.isfinite(oof).all():
        raise RuntimeError("New-classifier OOF probabilities are incomplete.")

    final_head = runtime.clone_classifier_head()
    final_head.fit(features, model_labels)
    return final_head, oof


def select_old_threshold(
    labels: np.ndarray,
    old_prob: np.ndarray,
    offline_threshold: float,
) -> dict:
    calibration_opt, calibration_opt_metrics = find_best_balanced_threshold(
        labels, old_prob, offline_threshold
    )
    applied_40_60 = float(np.clip(
        ORIGINAL_THRESHOLD_WEIGHT * offline_threshold
        + CALIBRATION_THRESHOLD_WEIGHT * calibration_opt,
        0.0,
        1.0,
    ))
    choice = choose_between_thresholds(
        labels,
        old_prob,
        offline_threshold,
        "offline",
        applied_40_60,
        "40:60_applied",
    )
    choice["calibration_optimal_threshold"] = float(calibration_opt)
    choice["calibration_optimal_metrics"] = calibration_opt_metrics
    choice["applied_40_60_threshold"] = float(applied_40_60)
    return choice


def select_new_threshold(labels: np.ndarray, new_oof_prob: np.ndarray) -> dict:
    oof_opt, oof_opt_metrics = find_best_balanced_threshold(labels, new_oof_prob, 0.5)
    choice = choose_between_thresholds(
        labels,
        new_oof_prob,
        0.5,
        "fixed_0.5",
        oof_opt,
        "calibration_oof_optimal",
    )
    choice["oof_optimal_threshold"] = float(oof_opt)
    choice["oof_optimal_metrics"] = oof_opt_metrics
    choice["oof_auc"] = float(roc_auc_score(labels, new_oof_prob))
    return choice


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
    return output_dir, eeg_base, log_path, calibration_log_path, calibration_summary_path


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
            pos=(0.82, 0.50),
            height=0.06,
            color=self.black,
            colorSpace="rgb255",
            units="norm",
        )

        # Ground-truth cue: top-center.
        self.target_text = visual.TextStim(
            win,
            text="",
            pos=(0.0, 0.50),
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
            radius=0.12,
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
        radius = 0.12
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

        # Arrow shaft. Only its LEFT/RIGHT position changes; size is fixed.
        self.shaft = visual.Rect(
            win,
            width=0.11,
            height=0.085,
            pos=(0, 0),
            fillColor=initial_fill,
            lineColor=initial_fill,  # no visible outline
            lineWidth=1,
            colorSpace="rgb255",
            units="height",
        )

        # Left-pointing triangle by default; ori=180 mirrors it for RIGHT.
        head_vertices = [
            (-0.07, 0.0),
            (0.045, 0.11),
            (0.045, -0.11),
        ]
        self.head = visual.ShapeStim(
            win,
            vertices=head_vertices,
            closeShape=True,
            pos=(0, 0),
            fillColor=initial_fill,
            lineColor=initial_fill,  # no visible outline
            lineWidth=1,
            colorSpace="rgb255",
            units="height",
        )

        self.start_text = visual.TextStim(
            win,
            text=(
                "New/Old Dynamic Fading Motor Imagery BCI Test\n\n"
                "먼저 20 trials (LEFT 10 / RIGHT 10) calibration을 수행합니다.\n"
                "Calibration에서는 제시된 방향의 손 움직임을 3초 동안 상상하세요.\n"
                "3초 MI를 0.5초씩 분할한 120개 window로 New classifier와 threshold를 결정합니다.\n"
                "각 참가자의 joblib에 저장된 frozen preprocessing/feature pipeline은 다시 학습하지 않습니다.\n"
                "본 실험은 40 trials이며 10-trial block마다 New/Old classifier가 교대로 적용됩니다.\n\n"
                "SPACE : 테스트 시작\n"
                "ESC : 종료"
            ),
            height=0.036,
            color=self.black,
            colorSpace="rgb255",
            wrapWidth=1.45,
            units="height",
        )

        self.result_text = visual.TextStim(
            win,
            text="",
            pos=(0, 0),
            height=0.038,
            color=self.black,
            colorSpace="rgb255",
            wrapWidth=1.7,
            units="height",
        )

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
        """Apply one color to circle/shaft/head while hiding their outlines."""
        self.circle.fillColor = color
        self.circle.lineColor = color
        self.shaft.fillColor = color
        self.shaft.lineColor = color
        self.head.fillColor = color
        self.head.lineColor = color

    def _set_direction(self, direction: str):
        """Keep the circle centered; only place/mirror the arrow LEFT or RIGHT."""
        direction = direction.upper()

        # The circle NEVER moves between Level 0 and Levels 1-4.
        self.circle.pos = (0, 0)

        if direction == "LEFT":
            self.shaft.pos = (-0.090, 0)
            self.head.pos = (-0.190, 0)
            self.head.ori = 0
        elif direction == "RIGHT":
            self.shaft.pos = (0.090, 0)
            self.head.pos = (0.190, 0)
            self.head.ori = 180
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

        # Same draw order as the preview UI: arrow first, centered circle last.
        # The circle slightly covers the shaft junction, making the cue look unified.
        self.shaft.draw()
        self.head.draw()
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

    def show_calibration_summary(
        self,
        offline_threshold: float,
        old_selected_threshold: float,
        old_threshold_source: str,
        new_selected_threshold: float,
        new_threshold_source: str,
        new_oof_auc: float,
        main_order_text: str,
    ):
        self.calibration_summary_text.text = (
            "Calibration 완료\n\n"
            f"Offline threshold : {offline_threshold:.4f}\n"
            f"Old threshold : {old_selected_threshold:.4f} ({old_threshold_source})\n"
            f"New threshold : {new_selected_threshold:.4f} ({new_threshold_source})\n"
            f"New OOF AUC : {new_oof_auc:.3f}\n"
            f"Main order : {main_order_text}\n\n"
            f"SPACE : {N_TRIALS}-trial 본 실험 시작\n"
            "ESC : 종료"
        )
        wait_for_space(self.calibration_summary_text, self.win)

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

    def show_final_results(self, results):
        n_success = sum(row["status"] == "SUCCESS" for row in results)
        n_fail = sum(row["status"] == "FAIL" for row in results)
        n_correct = sum(int(row.get("is_correct", 0)) for row in results)
        accuracy = (n_correct / len(results) * 100.0) if results else 0.0

        model_lines = []
        for model_name in ("NEW", "OLD"):
            subset = [row for row in results if row.get("model_mode") == model_name]
            if not subset:
                continue
            correct = sum(int(row.get("is_correct", 0)) for row in subset)
            success = sum(row["status"] == "SUCCESS" for row in subset)
            model_lines.append(
                f"{model_name}: correct {correct}/{len(subset)} "
                f"({100.0 * correct / len(subset):.1f}%), SUCCESS {success}/{len(subset)}"
            )

        self.result_text.text = (
            "온라인 테스트 완료\n\n"
            f"TOTAL correct : {n_correct}/{len(results)} ({accuracy:.1f}%)\n"
            f"SUCCESS : {n_success}/{len(results)}\n"
            f"FAIL : {n_fail}/{len(results)}\n"
            + "\n".join(model_lines)
        )
        event.clearEvents(eventType="keyboard")
        self.result_text.draw()
        self.win.flip()
        wait_with_escape(FINAL_RESULT_DURATION)

    def show_initial_relax(self, duration: float, explore):
        """Show the initial RELAX screen before the calibration block."""
        event.clearEvents(eventType="keyboard")
        self.initial_relax_text.draw()
        self.win.callOnFlip(explore.set_marker, INITIAL_RELAX_ONSET)
        self.win.flip()
        wait_with_escape(duration)

    def show_main_relax(self, duration: float, explore):
        """Show a RELAX screen immediately before the 40-trial main experiment."""
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
# Main
# =============================================================================
def main():
    args = parse_arguments()
    subject = args.subject.strip().lower()

    target_schedule = make_balanced_target_schedule(
        N_TRIALS, BLOCK_REST_INTERVAL, seed=args.seed
    )
    calibration_seed = None if args.seed is None else args.seed + 100003
    calibration_schedule = make_balanced_target_schedule(
        CALIBRATION_TRIALS, CALIBRATION_BLOCK_SIZE, seed=calibration_seed
    )
    main_model_order = list(MAIN_MODEL_ORDER)

    model_path, bundle = load_bundle(subject, args.model_file, args.model_dir)
    runtime = BundleRuntime(bundle)

    offline_threshold = _extract_offline_threshold(bundle)
    window_samples = int(round(CLASSIFICATION_WINDOW * runtime.fs))
    calibration_predictions = CALIBRATION_WINDOWS_PER_TRIAL
    if calibration_predictions * CLASSIFICATION_WINDOW != CALIBRATION_MI_DURATION:
        raise ValueError("Calibration MI duration must divide exactly into 0.5-s windows.")

    output_dir, eeg_base, log_path, calibration_log_path, calibration_summary_path = build_output_paths(args)
    for p in (log_path, calibration_log_path, calibration_summary_path):
        if p.exists():
            raise FileExistsError(f"{p} exists. Use a different -f name or --timestamp.")

    print("=" * 84)
    print("NEW/OLD DYNAMIC FADING MOTOR IMAGERY BCI TEST (FIXED NEW -> OLD -> NEW -> OLD)")
    print("=" * 84)
    print(f"Subject              : {subject}")
    print(f"Model                : {model_path}")
    print(f"Sampling rate        : {runtime.fs:.0f} Hz")
    print(f"Channels             : {runtime.selected_channels}")
    epoch_start = bundle["epoch"].get("actual_start_sec", bundle["epoch"].get("start_sec", "n/a"))
    epoch_end = bundle["epoch"].get("actual_end_sec", bundle["epoch"].get("end_sec", "n/a"))
    print(f"Bundle schema        : {bundle.get('schema_version', 'unspecified')}")
    print(f"Predictor kind       : {runtime.predictor_kind or 'unspecified'}")
    print(f"Offline train epoch  : {epoch_start}-{epoch_end} s")
    print(f"Frozen pipeline      : {runtime.pipeline_summary()}")
    print(f"Stored clipping      : {runtime.clip_description}")
    print(f"Offline threshold    : {offline_threshold:.6f}")
    print(f"Calibration          : {CALIBRATION_TRIALS} trials x 3.0 s -> 120 x 0.5-s windows")
    print(f"Calibration OOF      : {CALIBRATION_OOF_FOLDS}-fold, grouped by trial")
    print(f"Main                 : {N_TRIALS} trials = 4 blocks x 10")
    print(f"Main model order     : {' -> '.join(main_model_order)}")
    print("Old threshold choice : Offline vs 40:60 Applied (higher calibration BA)")
    print("New threshold choice : 0.5 vs Calibration OOF optimal (higher OOF BA)")
    print("=" * 84)

    win = visual.Window(
        size=(3440, 1440),
        fullscr=not args.windowed,
        screen=args.screen,
        units="height",
        color=(255, 255, 255),
        colorSpace="rgb255",
        allowGUI=args.windowed,
    )
    ui = OnlineTestUI(win)

    explore = Explore()
    connected = False
    recording = False
    subscribed = False
    global_clock = core.Clock()
    results = []

    calibration_epochs = []
    calibration_window_targets = []
    calibration_window_trial_ids = []
    calibration_trial_metadata = []

    calibration_log_fields = [
        "subject", "trial", "target_direction",
        "old_probability_sequence", "old_trial_median_probability",
        "new_oof_probability_sequence", "new_oof_trial_median_probability",
        "calibration_rest_onset_s", "calibration_rest_stream_sample",
        "calibration_cue_onset_s", "calibration_cue_stream_sample",
    ]

    log_fields = [
        "subject", "trial", "block", "model_mode", "target_direction",
        "threshold_used", "threshold_source",
        "offline_threshold", "old_selected_threshold", "new_selected_threshold",
        "prediction_sequence", "predicted_label_sequence", "right_probability_sequence",
        "selection_level_sequence", "candidate_sequence",
        "initial_candidate_decision", "candidate_decision", "final_decision",
        "is_correct", "final_selection_level", "n_predictions",
        "decision_time_s", "actual_wall_time_s", "status",
        "trial_rest_onset_s", "classification_onset_s",
        "classification_onset_stream_sample", "outcome_onset_s",
    ]

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
            raise RuntimeError("No live ExG packets were received from the Explore device.")

        with (
            calibration_log_path.open("x", newline="", encoding="utf-8-sig") as calibration_log_file,
            log_path.open("x", newline="", encoding="utf-8-sig") as log_file,
        ):
            calibration_writer = csv.DictWriter(calibration_log_file, fieldnames=calibration_log_fields)
            calibration_writer.writeheader()
            writer = csv.DictWriter(log_file, fieldnames=log_fields)
            writer.writeheader()

            wait_for_space(ui.start_text, win)
            global_clock.reset()
            explore.set_marker(SESSION_START)
            ui.show_initial_relax(INITIAL_RELAX_DURATION, explore)

            # =================================================================
            # Calibration: 20 x 3 s -> 120 non-overlapping 0.5-s windows
            # =================================================================
            explore.set_marker(CALIBRATION_START)
            print("\n" + "=" * 84)
            print("20-TRIAL CALIBRATION: COLLECT 120 WINDOWS")
            print("=" * 84)

            for calibration_trial in range(1, CALIBRATION_TRIALS + 1):
                target_direction = calibration_schedule[calibration_trial - 1]
                rest_onset, rest_sample = ui.show_calibration_rest(
                    calibration_trial, explore, global_clock, runtime
                )
                cue_onset, calibration_start_sample = ui.begin_calibration_trial(
                    calibration_trial, target_direction, explore, global_clock, runtime
                )

                label = (
                    runtime.output_spec["right_label"]
                    if target_direction == "RIGHT"
                    else runtime.output_spec["left_label"]
                )
                for window_index in range(calibration_predictions):
                    window_start = calibration_start_sample + window_index * window_samples
                    epoch = runtime.get_window_epoch(window_start, window_samples, timeout=2.0)
                    calibration_epochs.append(np.array(epoch, copy=True))
                    calibration_window_targets.append(label)
                    calibration_window_trial_ids.append(calibration_trial)

                calibration_trial_metadata.append({
                    "trial": calibration_trial,
                    "target_direction": target_direction,
                    "calibration_rest_onset_s": rest_onset,
                    "calibration_rest_stream_sample": rest_sample,
                    "calibration_cue_onset_s": cue_onset,
                    "calibration_cue_stream_sample": calibration_start_sample,
                })
                print(
                    f"Calibration {calibration_trial:02d}/{CALIBRATION_TRIALS} | "
                    f"target={target_direction:<5} | 6 windows collected"
                )
                if (
                    calibration_trial % CALIBRATION_BLOCK_SIZE == 0
                    and calibration_trial < CALIBRATION_TRIALS
                ):
                    ui.show_calibration_block_rest(CALIBRATION_BLOCK_REST_DURATION, explore)

            explore.set_marker(CALIBRATION_END)

            X_cal = np.concatenate(calibration_epochs, axis=0)
            y_model = np.asarray(calibration_window_targets)
            trial_ids = np.asarray(calibration_window_trial_ids, dtype=int)
            if X_cal.shape[0] != CALIBRATION_TRIALS * CALIBRATION_WINDOWS_PER_TRIAL:
                raise RuntimeError(f"Expected 120 calibration windows, got {X_cal.shape[0]}.")

            # Participant-specific frozen path read entirely from this participant's joblib.
            calibration_features = runtime.extract_frozen_features(X_cal)

            # Threshold metrics always use protocol binary coding (LEFT=0, RIGHT=1),
            # while classifier fitting preserves the participant model's actual labels.
            y_binary = (y_model == runtime.output_spec["right_label"]).astype(int)

            # OLD classifier remains exactly the fitted offline final classifier.
            old_classifier = runtime.old_classifier
            old_prob = runtime.right_probabilities_from_features(old_classifier, calibration_features)
            old_choice = select_old_threshold(y_binary, old_prob, offline_threshold)

            # NEW classifier: clone only this participant's final classifier type and
            # train that head on today's 120 windows. All prior frozen transforms stay fixed.
            ui.show_finetuning()
            new_classifier, new_oof_prob = build_new_classifier_and_oof(
                runtime,
                calibration_features,
                y_model,
                trial_ids,
                calibration_seed,
            )
            new_choice = select_new_threshold(y_binary, new_oof_prob)

            old_selected_threshold = float(old_choice["threshold"])
            new_selected_threshold = float(new_choice["threshold"])

            # Per-trial calibration log (probability sequences are 6 windows/trial).
            for meta in calibration_trial_metadata:
                tid = int(meta["trial"])
                mask = trial_ids == tid
                old_seq = old_prob[mask]
                new_seq = new_oof_prob[mask]
                calibration_writer.writerow({
                    "subject": subject,
                    "trial": tid,
                    "target_direction": meta["target_direction"],
                    "old_probability_sequence": _csv_float_sequence(old_seq),
                    "old_trial_median_probability": f"{float(np.median(old_seq)):.8f}",
                    "new_oof_probability_sequence": _csv_float_sequence(new_seq),
                    "new_oof_trial_median_probability": f"{float(np.median(new_seq)):.8f}",
                    "calibration_rest_onset_s": f"{meta['calibration_rest_onset_s']:.6f}",
                    "calibration_rest_stream_sample": int(meta["calibration_rest_stream_sample"]),
                    "calibration_cue_onset_s": f"{meta['calibration_cue_onset_s']:.6f}",
                    "calibration_cue_stream_sample": int(meta["calibration_cue_stream_sample"]),
                })
            calibration_log_file.flush()

            with calibration_summary_path.open("x", newline="", encoding="utf-8-sig") as f:
                fields = [
                    "subject", "bundle_schema", "predictor_kind", "sampling_rate_hz",
                    "selected_channels", "frozen_pipeline", "stored_clipping",
                    "n_calibration_trials", "n_calibration_windows",
                    "offline_threshold",
                    "old_calibration_optimal_threshold", "old_40_60_threshold",
                    "old_ba_offline", "old_ba_40_60", "old_selected_threshold", "old_threshold_source",
                    "new_oof_auc", "new_oof_optimal_threshold",
                    "new_ba_at_0.5", "new_ba_oof_optimal",
                    "new_selected_threshold", "new_threshold_source",
                    "main_order",
                ]
                sw = csv.DictWriter(f, fieldnames=fields)
                sw.writeheader()
                sw.writerow({
                    "subject": subject,
                    "bundle_schema": bundle.get("schema_version", "unspecified"),
                    "predictor_kind": runtime.predictor_kind or "unspecified",
                    "sampling_rate_hz": f"{runtime.fs:.8g}",
                    "selected_channels": ",".join(runtime.selected_channels),
                    "frozen_pipeline": runtime.pipeline_summary(),
                    "stored_clipping": runtime.clip_description,
                    "n_calibration_trials": CALIBRATION_TRIALS,
                    "n_calibration_windows": len(y_model),
                    "offline_threshold": f"{offline_threshold:.8f}",
                    "old_calibration_optimal_threshold": f"{old_choice['calibration_optimal_threshold']:.8f}",
                    "old_40_60_threshold": f"{old_choice['applied_40_60_threshold']:.8f}",
                    "old_ba_offline": f"{old_choice['candidate_a']['balanced_accuracy']:.8f}",
                    "old_ba_40_60": f"{old_choice['candidate_b']['balanced_accuracy']:.8f}",
                    "old_selected_threshold": f"{old_selected_threshold:.8f}",
                    "old_threshold_source": old_choice["source"],
                    "new_oof_auc": f"{new_choice['oof_auc']:.8f}",
                    "new_oof_optimal_threshold": f"{new_choice['oof_optimal_threshold']:.8f}",
                    "new_ba_at_0.5": f"{new_choice['candidate_a']['balanced_accuracy']:.8f}",
                    "new_ba_oof_optimal": f"{new_choice['candidate_b']['balanced_accuracy']:.8f}",
                    "new_selected_threshold": f"{new_selected_threshold:.8f}",
                    "new_threshold_source": new_choice["source"],
                    "main_order": "->".join(main_model_order),
                })

            print("\n" + "=" * 84)
            print("CALIBRATION RESULT")
            print("=" * 84)
            print(f"OLD offline threshold       : {offline_threshold:.6f} | BA={old_choice['candidate_a']['balanced_accuracy']:.4f}")
            print(f"OLD 40:60 threshold         : {old_choice['applied_40_60_threshold']:.6f} | BA={old_choice['candidate_b']['balanced_accuracy']:.4f}")
            print(f"OLD selected                : {old_selected_threshold:.6f} ({old_choice['source']})")
            print(f"NEW 0.5                     : 0.500000 | OOF BA={new_choice['candidate_a']['balanced_accuracy']:.4f}")
            print(f"NEW OOF optimal             : {new_choice['oof_optimal_threshold']:.6f} | OOF BA={new_choice['candidate_b']['balanced_accuracy']:.4f}")
            print(f"NEW OOF AUC                 : {new_choice['oof_auc']:.4f}")
            print(f"NEW selected                : {new_selected_threshold:.6f} ({new_choice['source']})")
            print(f"Main order                  : {' -> '.join(main_model_order)}")
            print("=" * 84)

            ui.show_calibration_summary(
                offline_threshold,
                old_selected_threshold,
                old_choice["source"],
                new_selected_threshold,
                new_choice["source"],
                new_choice["oof_auc"],
                " -> ".join(main_model_order),
            )

            ui.show_main_relax(MAIN_RELAX_DURATION, explore)
            explore.set_marker(MAIN_EXPERIMENT_START)

            # =================================================================
            # Main 40 trials: 10-trial blocks alternating NEW / OLD
            # =================================================================
            for trial_number in range(1, N_TRIALS + 1):
                target_direction = target_schedule[trial_number - 1]
                block_index = (trial_number - 1) // BLOCK_REST_INTERVAL
                model_mode = main_model_order[block_index]
                if model_mode == "NEW":
                    classifier = new_classifier
                    threshold_used = new_selected_threshold
                    threshold_source = new_choice["source"]
                else:
                    classifier = old_classifier
                    threshold_used = old_selected_threshold
                    threshold_source = old_choice["source"]

                trial_rest_onset = ui.show_trial_rest(
                    trial_number, target_direction, explore, global_clock
                )
                classification_onset, classification_start_sample = ui.begin_classification(
                    trial_number, target_direction, explore, global_clock, runtime
                )

                candidate = None
                selection_level = 0
                final_decision = None
                status = None
                outcome_onset = None
                prediction_sequence = []
                predicted_label_sequence = []
                probability_sequence = []
                level_sequence = []
                candidate_sequence = []
                initial_candidate = None
                actual_wall_time = None
                decision_time = None

                for prediction_index in range(1, MAX_PREDICTIONS + 1):
                    window_start = classification_start_sample + (prediction_index - 1) * window_samples
                    epoch = runtime.get_window_epoch(window_start, window_samples, timeout=2.0)
                    predicted_label, predicted_direction, right_probability = runtime.predict_with_classifier(
                        epoch, classifier, threshold_used
                    )
                    if predicted_direction not in {"LEFT", "RIGHT"}:
                        raise RuntimeError(f"Unexpected prediction {predicted_direction!r}.")

                    explore.set_marker(PRED_LEFT_ONSET if predicted_direction == "LEFT" else PRED_RIGHT_ONSET)
                    prediction_sequence.append("L" if predicted_direction == "LEFT" else "R")
                    predicted_label_sequence.append(str(predicted_label))
                    probability_sequence.append(f"{right_probability:.8f}")

                    # Dynamic Fading rule unchanged from the original code.
                    if selection_level == 0:
                        candidate = predicted_direction
                        if initial_candidate is None:
                            initial_candidate = candidate
                        selection_level = 1
                    elif predicted_direction == candidate:
                        selection_level = min(4, selection_level + 1)
                    else:
                        selection_level = max(0, selection_level - 1)

                    level_sequence.append(str(selection_level))
                    candidate_sequence.append(candidate or "")
                    decision_time = prediction_index * CLASSIFICATION_WINDOW
                    actual_wall_time = global_clock.getTime() - classification_onset

                    if selection_level == 4:
                        status = "SUCCESS"
                        final_decision = candidate
                        outcome_onset = ui.show_outcome(
                            trial_number, candidate, target_direction, status, explore, global_clock
                        )
                        break

                    ui.show_level(
                        trial_number, selection_level, candidate, target_direction, explore, global_clock
                    )

                if status is None:
                    status = "FAIL"
                    final_decision = None
                    decision_time = MAX_CLASSIFICATION_DURATION
                    actual_wall_time = global_clock.getTime() - classification_onset
                    outcome_onset = ui.show_outcome(
                        trial_number, candidate, target_direction, status, explore, global_clock
                    )

                is_correct = (
                    final_decision == target_direction
                    if final_decision in {"LEFT", "RIGHT"}
                    else False
                )

                row = {
                    "subject": subject,
                    "trial": trial_number,
                    "block": block_index + 1,
                    "model_mode": model_mode,
                    "target_direction": target_direction,
                    "threshold_used": f"{threshold_used:.8f}",
                    "threshold_source": threshold_source,
                    "offline_threshold": f"{offline_threshold:.8f}",
                    "old_selected_threshold": f"{old_selected_threshold:.8f}",
                    "new_selected_threshold": f"{new_selected_threshold:.8f}",
                    "prediction_sequence": ",".join(prediction_sequence),
                    "predicted_label_sequence": ",".join(predicted_label_sequence),
                    "right_probability_sequence": ",".join(probability_sequence),
                    "selection_level_sequence": ",".join(level_sequence),
                    "candidate_sequence": ",".join(candidate_sequence),
                    "initial_candidate_decision": initial_candidate or "",
                    "candidate_decision": candidate or "",
                    "final_decision": final_decision or "",
                    "is_correct": int(is_correct),
                    "final_selection_level": int(selection_level),
                    "n_predictions": len(prediction_sequence),
                    "decision_time_s": f"{float(decision_time):.3f}",
                    "actual_wall_time_s": f"{float(actual_wall_time):.6f}",
                    "status": status,
                    "trial_rest_onset_s": f"{trial_rest_onset:.6f}",
                    "classification_onset_s": f"{classification_onset:.6f}",
                    "classification_onset_stream_sample": int(classification_start_sample),
                    "outcome_onset_s": f"{outcome_onset:.6f}",
                }
                results.append(row)
                writer.writerow(row)
                log_file.flush()

                print(
                    f"Trial {trial_number:02d}/{N_TRIALS} | block={block_index + 1} {model_mode:<3} | "
                    f"target={target_direction:<5} | final={(final_decision or 'NONE'):<5} | "
                    f"level={selection_level} | time={float(decision_time):>4.1f}s | "
                    f"correct={int(is_correct)} | th={threshold_used:.4f} | "
                    f"pred={''.join(prediction_sequence)}"
                )

                if trial_number % BLOCK_REST_INTERVAL == 0 and trial_number < N_TRIALS:
                    next_block = block_index + 1
                    print(
                        f"\n>>> Block {block_index + 1} complete. "
                        f"Rest {BLOCK_REST_DURATION:.0f}s; next model={main_model_order[next_block]}\n"
                    )
                    ui.show_block_rest(BLOCK_REST_DURATION, explore)

            explore.set_marker(SESSION_END)
            ui.show_final_results(results)

    except ExperimentAbort:
        if connected:
            try:
                explore.set_marker(EXPERIMENT_ABORTED)
            except Exception:
                pass
        print("Online test aborted with Escape.")

    finally:
        if subscribed and connected:
            try:
                explore.stream_processor.unsubscribe(callback=runtime.process_packet, topic=TOPICS.raw_ExG)
            except Exception as exc:
                print(f"Could not unsubscribe cleanly: {exc}")
        if recording:
            try:
                explore.stop_recording()
            except Exception as exc:
                print(f"Could not stop recording cleanly: {exc}")
        if connected:
            try:
                explore.disconnect()
            except Exception as exc:
                print(f"Could not disconnect cleanly: {exc}")
        win.close()
        print(f"Data saved in: {output_dir}")
        if results:
            for model_name in ("NEW", "OLD"):
                subset = [r for r in results if r.get("model_mode") == model_name]
                if subset:
                    correct = sum(int(r["is_correct"]) for r in subset)
                    success = sum(r["status"] == "SUCCESS" for r in subset)
                    print(
                        f"{model_name}: correct={correct}/{len(subset)} "
                        f"({100.0 * correct / len(subset):.1f}%), SUCCESS={success}/{len(subset)}"
                    )
    core.quit()


if __name__ == "__main__":
    main()
