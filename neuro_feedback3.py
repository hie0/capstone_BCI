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

from psychopy import core, event, visual
from explorepy import Explore
from explorepy.stream_processor import TOPICS


# =============================================================================
# Experiment markers
# =============================================================================
SESSION_START = 1
INITIAL_RELAX_ONSET = 20
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
N_TRIALS = 60
EXPECTED_SAMPLING_RATE = 250.0
CLASSIFICATION_WINDOW = 0.5
INITIAL_RELAX_DURATION = 5.0
TRIAL_REST_DURATION = 1.0
BLOCK_REST_INTERVAL = 10
BLOCK_REST_DURATION = 5.0
MAX_CLASSIFICATION_DURATION = 15.0
MAX_PREDICTIONS = int(MAX_CLASSIFICATION_DURATION / CLASSIFICATION_WINDOW)  # 30
RESULT_DISPLAY_DURATION = 1.0
FINAL_RESULT_DURATION = 5.0

SCHEMA_VERSION = "bci_bundle_v1"


class ExperimentAbort(Exception):
    """Raised when Escape is pressed."""


# =============================================================================
# Command-line arguments
# =============================================================================
def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Online free-choice left/right Motor Imagery BCI test with Dynamic Fading "
            "neurofeedback using a participant-specific BCI bundle (.joblib)."
        )
    )
    parser.add_argument(
        "-n",
        "--name",
        dest="device_name",
        required=True,
        help="Explore EEG device name, e.g. Explore_DABP.",
    )
    parser.add_argument(
        "-f",
        "--filename",
        dest="filename",
        required=True,
        help="Base name for the online-test recording/session.",
    )
    parser.add_argument(
        "--subject",
        required=True,
        help=(
            "Participant id. The program loads <subject>_model.joblib automatically "
            "without subject-specific preprocessing branches."
        ),
    )
    parser.add_argument(
        "--model-dir",
        default="models",
        help="Directory containing <subject>_model.joblib. Default: models",
    )
    parser.add_argument(
        "-o",
        "--outdir",
        default="data",
        help="Root directory for online-test data. Default: data",
    )
    parser.add_argument(
        "--timestamp",
        action="store_true",
        help="Append a timestamp to the session folder name.",
    )
    # Optional seed for reproducible target-order randomization.
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=(
            "Random seed for block-balanced target assignment. "
            "Each 10-trial block contains 5 LEFT and 5 RIGHT targets."
        ),
    )
    parser.add_argument(
        "--screen",
        type=int,
        default=0,
        help="PsychoPy monitor number. Default: 0",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Run in a window rather than full-screen.",
    )
    return parser.parse_args()


# =============================================================================
# Trial target schedule
# =============================================================================
def make_balanced_target_schedule(n_trials: int, block_size: int, seed: int | None = None) -> list[str]:
    """Create a block-balanced LEFT/RIGHT target schedule.

    Each block contains exactly half LEFT and half RIGHT trials, shuffled randomly.
    For the current experiment: 60 trials -> 6 blocks of 10 -> 5 LEFT + 5 RIGHT per block.
    """
    n_trials = int(n_trials)
    block_size = int(block_size)

    if n_trials <= 0 or block_size <= 0:
        raise ValueError("n_trials and block_size must be positive integers.")
    if n_trials % block_size != 0:
        raise ValueError(
            f"N_TRIALS ({n_trials}) must be divisible by block_size ({block_size})."
        )
    if block_size % 2 != 0:
        raise ValueError("block_size must be even to assign equal LEFT/RIGHT targets.")

    rng = random.Random(seed)
    half = block_size // 2
    schedule: list[str] = []

    for _ in range(n_trials // block_size):
        block = ["LEFT"] * half + ["RIGHT"] * half
        rng.shuffle(block)
        schedule.extend(block)

    return schedule


# =============================================================================
# Bundle loading / validation
# =============================================================================
def resolve_model_path(subject: str, model_dir: str) -> Path:
    """Resolve <subject>_model.joblib using a generic filename convention."""
    subject = subject.strip().lower()
    filename = f"{subject}_model.joblib"

    script_dir = Path(__file__).resolve().parent
    candidates = [
        Path(model_dir).expanduser() / filename,
        script_dir / model_dir / filename,
        script_dir / filename,
    ]

    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate

    searched = "\n  - ".join(str(p) for p in candidates)
    raise FileNotFoundError(
        f"Could not find model bundle for subject '{subject}'.\n"
        f"Expected file: {filename}\n"
        f"Searched:\n  - {searched}"
    )


def load_bundle(subject: str, model_dir: str):
    model_path = resolve_model_path(subject, model_dir)
    bundle = joblib.load(model_path)

    if not isinstance(bundle, dict):
        raise TypeError(
            f"{model_path.name} is not a BCI bundle dictionary. "
            "Regenerate it with the common BCI bundle v1 model script."
        )

    if bundle.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported bundle schema: {bundle.get('schema_version')!r}. "
            f"Expected {SCHEMA_VERSION!r}."
        )

    requested = subject.strip().lower()
    bundled = str(bundle.get("participant", "")).lower()
    if bundled != requested:
        raise ValueError(
            f"Subject mismatch: --subject={requested!r}, but bundle participant={bundled!r}."
        )

    if not bool(bundle.get("metadata", {}).get("online_ready", False)):
        notes = bundle.get("metadata", {}).get("notes", {})
        blocker = notes.get("online_blocker") or notes.get("requires_online_calibration")
        raise RuntimeError(
            f"{requested}_model.joblib is marked online_ready=False.\n"
            "This online test intentionally stops rather than applying preprocessing "
            "that differs from training.\n"
            f"Bundle note: {blocker}"
        )

    validate_bundle_structure(bundle)
    return model_path, bundle


def validate_bundle_structure(bundle: dict):
    for key in (
        "participant",
        "sampling_rate",
        "input",
        "preprocessing",
        "epoch",
        "predictor",
        "output",
        "metadata",
    ):
        if key not in bundle:
            raise KeyError(f"Bundle is missing required key: {key}")

    fs = float(bundle["sampling_rate"])
    if abs(fs - EXPECTED_SAMPLING_RATE) > 1e-9:
        raise ValueError(
            f"This Dynamic Fading experiment requires {EXPECTED_SAMPLING_RATE:.0f} Hz, "
            f"but the bundle uses {fs:.3f} Hz."
        )

    start_sec = float(bundle["epoch"]["start_sec"])
    end_sec = float(bundle["epoch"]["end_sec"])
    if not (0.0 <= start_sec < end_sec):
        raise ValueError(f"Invalid epoch range: {start_sec} to {end_sec} sec")

    epoch_duration = end_sec - start_sec
    expected_samples = int(round(CLASSIFICATION_WINDOW * fs))
    epoch_samples = int(bundle["epoch"]["n_samples"])

    if abs(epoch_duration - CLASSIFICATION_WINDOW) > 1e-9 or epoch_samples != expected_samples:
        raise ValueError(
            "The online experiment classifies non-overlapping 0.5-s EEG epochs. "
            f"The loaded bundle instead specifies {start_sec:.3f}-{end_sec:.3f} s "
            f"({epoch_duration:.3f} s, {epoch_samples} samples). "
            f"Retrain/export the offline model with a {CLASSIFICATION_WINDOW:.1f}-s "
            f"epoch ({expected_samples} samples at {fs:.0f} Hz)."
        )


# =============================================================================
# Generic bundle-driven real-time EEG processor
# =============================================================================
class BundleRuntime:
    """
    Apply streaming preprocessing from bundle['preprocessing']['operations'].

    There are no participant-name branches here. Runtime behavior comes entirely
    from the bundle operations and predictor kind.
    """

    def __init__(self, bundle: dict):
        self.bundle = bundle
        self.fs = float(bundle["sampling_rate"])
        self.input_spec = bundle["input"]
        self.operations = list(bundle["preprocessing"]["operations"])
        self.epoch_spec = bundle["epoch"]
        self.predictor = bundle["predictor"]
        self.output_spec = bundle["output"]

        self.all_channel_names = list(self.input_spec["all_channel_names"])
        self.selected_channel_indices = [
            int(i) for i in self.input_spec["selected_channel_indices"]
        ]
        self.selected_channels = list(self.input_spec["selected_channels"])

        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._chunks: list[np.ndarray] = []
        self._chunk_starts: list[int] = []
        self._sample_count = 0
        self._filter_zi: dict[object, np.ndarray] = {}
        self._stream_error: Exception | None = None

        self._validate_supported_operations()

    def _validate_supported_operations(self):
        supported_stream_ops = {
            "select_channels",
            "unit_scale",
            "sos_filter",
            "sos_filter_bank",
            "car_reference",
        }
        unsupported = []
        for op in self.operations:
            scope = op.get("scope", "stream")
            name = op.get("op")
            if scope == "stream" and name not in supported_stream_ops:
                unsupported.append(name)
            elif scope != "stream":
                # Current online-ready bundles should have their required live
                # preprocessing represented as stream operations.
                unsupported.append(f"{name} (scope={scope})")

        if unsupported:
            raise NotImplementedError(
                "This bundle contains preprocessing operations that cannot be "
                "reproduced by the current real-time runtime: "
                + ", ".join(map(str, unsupported))
            )

        kind = self.predictor.get("kind")
        if kind not in {"sklearn_pipeline", "hybrid_fbriemann_csp"}:
            raise NotImplementedError(
                f"Predictor kind {kind!r} is not currently online-supported. "
                "The model should only be marked online_ready=True after a matching "
                "runtime implementation exists."
            )

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
        """ExplorePy raw_ExG callback."""
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

        # ExplorePy commonly returns channels x samples. Normalize to samples x channels.
        if arr.shape[0] == n_expected and arr.shape[1] != n_expected:
            arr = arr.T
        elif arr.shape[1] == n_expected:
            pass
        elif arr.shape[0] <= 32 and arr.shape[1] > arr.shape[0]:
            arr = arr.T

        if arr.shape[1] < n_expected:
            raise ValueError(
                f"The bundle expects {n_expected} ExG channels, but the incoming "
                f"packet has shape {arr.shape}."
            )

        # If the device exposes additional channels, the bundle defines which
        # first channel layout was used for training.
        arr = arr[:, :n_expected]

        if not np.isfinite(arr).all():
            raise ValueError("Incoming EEG packet contains NaN or Inf.")

        return arr

    def _apply_stream_operations(self, data: np.ndarray) -> np.ndarray:
        y = np.asarray(data, dtype=np.float64)

        for op_index, operation in enumerate(self.operations):
            name = operation["op"]
            params = operation.get("params", {})

            if name == "select_channels":
                indices = [int(i) for i in params["indices"]]
                y = y[:, indices]

            elif name == "unit_scale":
                y = y * float(params["factor"])

            elif name == "car_reference":
                y = y - np.mean(y, axis=1, keepdims=True)

            elif name == "sos_filter":
                if y.ndim != 2:
                    raise ValueError("sos_filter expects samples x channels input.")
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
                raise NotImplementedError(f"Unsupported stream operation: {name}")

        # Some bundles describe channel selection only in input metadata rather
        # than as an explicit operation. Apply it once if needed.
        expected_n = len(self.selected_channels)
        if y.ndim == 2:
            channel_axis_size = y.shape[1]
            if channel_axis_size != expected_n:
                if channel_axis_size == len(self.all_channel_names):
                    y = y[:, self.selected_channel_indices]
                else:
                    raise ValueError(
                        f"Processed channel count is {channel_axis_size}, expected {expected_n}."
                    )
        elif y.ndim == 3:
            channel_axis_size = y.shape[2]
            if channel_axis_size != expected_n:
                if channel_axis_size == len(self.all_channel_names):
                    y = y[:, :, self.selected_channel_indices]
                else:
                    raise ValueError(
                        f"Processed channel count is {channel_axis_size}, expected {expected_n}."
                    )
        else:
            raise ValueError(f"Unexpected processed EEG shape: {y.shape}")

        return y

    def mark_stream_sample(self) -> int:
        """Return the absolute processed-sample index at the current visual flip."""
        with self._lock:
            if self._stream_error is not None:
                raise RuntimeError("EEG stream callback failed") from self._stream_error
            return int(self._sample_count)

    def _slice_samples_locked(self, start: int, stop: int) -> np.ndarray:
        """Slice [start:stop] without concatenating the entire recording each time."""
        if start < 0 or stop <= start:
            raise ValueError(f"Invalid sample range: {start}:{stop}")
        if not self._chunks:
            raise RuntimeError("No processed EEG samples are available.")

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
                raise RuntimeError(
                    f"Gap in processed EEG stream: expected sample {cursor}, "
                    f"next chunk starts at {chunk_start}."
                )

            local_start = cursor - chunk_start
            local_stop = min(stop, chunk_stop) - chunk_start
            parts.append(chunk[local_start:local_stop])
            cursor = chunk_start + local_stop
            idx += 1

        if cursor != stop:
            raise RuntimeError(
                f"Could not assemble EEG samples {start}:{stop}; reached only {cursor}."
            )

        return np.concatenate(parts, axis=0)

    def get_window_epoch(
        self,
        start_sample: int,
        n_samples: int,
        timeout: float = 2.0,
    ) -> np.ndarray:
        """Return one exact non-overlapping model window from the continuous stream."""
        start = int(start_sample)
        n_samples = int(n_samples)
        stop = start + n_samples

        expected_samples = int(self.epoch_spec["n_samples"])
        if n_samples != expected_samples:
            raise ValueError(
                f"Requested {n_samples} samples, but the model expects {expected_samples}."
            )

        deadline = time.monotonic() + timeout
        with self._condition:
            while self._sample_count < stop:
                if self._stream_error is not None:
                    raise RuntimeError("EEG stream callback failed") from self._stream_error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Not enough EEG samples for prediction: have {self._sample_count}, "
                        f"need {stop}. Check device streaming/sampling rate."
                    )
                self._condition.wait(timeout=min(0.05, remaining))

            epoch = self._slice_samples_locked(start, stop)

        n_channels = len(self.selected_channels)
        if epoch.ndim == 2:
            if epoch.shape != (n_samples, n_channels):
                raise RuntimeError(
                    f"Epoch shape mismatch: got {epoch.shape}, expected "
                    f"({n_samples}, {n_channels})."
                )
            return epoch.T[np.newaxis, :, :]

        if epoch.ndim == 3:
            n_bands = epoch.shape[1]
            if epoch.shape != (n_samples, n_bands, n_channels):
                raise RuntimeError(
                    f"Filter-bank epoch shape mismatch: got {epoch.shape}."
                )
            return np.transpose(epoch, (1, 2, 0))[np.newaxis, :, :, :]

        raise RuntimeError(f"Unexpected epoch dimensionality: {epoch.shape}")

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

    def _hybrid_features(self, epoch: np.ndarray) -> np.ndarray:
        state = self.predictor["objects"]["feature_state"]
        if state is None:
            raise RuntimeError("Hybrid predictor requires feature_state.")
        shrink = float(state["shrink"])
        ref_covs = state["ref_covs"]
        csps = state["csps"]
        n_bands = epoch.shape[1]
        if len(ref_covs) != n_bands or len(csps) != n_bands:
            raise RuntimeError("Hybrid feature_state band count does not match epoch.")

        ts_features = []
        csp_features = []
        for b in range(n_bands):
            X_b = epoch[:, b, :, :]
            covs = self._compute_shrinkage_covariances(X_b, shrink)
            ts_features.append(
                self._vectorized_tangent_space(covs, np.asarray(ref_covs[b], dtype=float))
            )
            csp_features.append(csps[b].transform(X_b))

        return np.hstack([np.hstack(ts_features), np.hstack(csp_features)])

    def predict(self, epoch: np.ndarray) -> tuple[object, str, float | None]:
        kind = self.predictor["kind"]
        model = self.predictor["objects"]["model"]
        if model is None:
            raise RuntimeError("Bundle predictor.objects.model is None.")

        if kind == "sklearn_pipeline":
            model_input = epoch
        elif kind == "hybrid_fbriemann_csp":
            features = self._hybrid_features(epoch)
            scaler = self.predictor["objects"].get("scaler")
            model_input = scaler.transform(features) if scaler is not None else features
        else:
            raise NotImplementedError(f"Unsupported predictor kind: {kind}")

        decision_mode = self.predictor.get("decision_mode", "predict")
        left_label = self.output_spec["left_label"]
        right_label = self.output_spec["right_label"]
        probability = None

        if decision_mode == "predict":
            label = model.predict(model_input)[0]

        elif decision_mode == "predict_proba_threshold":
            threshold = float(self.predictor.get("threshold", 0.5))
            proba = model.predict_proba(model_input)[0]
            classes = np.asarray(model.classes_)
            right_matches = np.flatnonzero(classes == right_label)
            if len(right_matches) != 1:
                raise RuntimeError(
                    f"Could not locate right label {right_label!r} in model.classes_={classes}."
                )
            probability = float(proba[int(right_matches[0])])
            label = right_label if probability >= threshold else left_label

        else:
            raise NotImplementedError(f"Unsupported decision_mode: {decision_mode}")

        direction_map = self.output_spec["label_to_direction"]
        if label in direction_map:
            direction = direction_map[label]
        elif str(label) in direction_map:
            direction = direction_map[str(label)]
        else:
            raise KeyError(f"Prediction label {label!r} is absent from label_to_direction.")

        return label, str(direction).upper(), probability


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
    return output_dir, eeg_base, log_path


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
                "Dynamic Fading Motor Imagery BCI Test\n\n"
                "각 Trial 상단에 제시된 정답 방향(LEFT 또는 RIGHT)의 손 움직임을 상상하세요.\n"
                "중앙 cue의 색상 변화가 실시간 분류 결과를 반영합니다.\n"
                "Level 0에서는 다음 분류 결과가 새로운 Candidate 방향이 됩니다.\n\n"
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
        left_final = sum(row["final_decision"] == "LEFT" for row in results)
        right_final = sum(row["final_decision"] == "RIGHT" for row in results)
        success_times = [
            float(row["decision_time_s"])
            for row in results
            if row["status"] == "SUCCESS"
        ]
        mean_time = float(np.mean(success_times)) if success_times else float("nan")
        mean_time_text = f"{mean_time:.2f} s" if success_times else "N/A"
        n_correct = sum(int(row.get("is_correct", 0)) for row in results)
        accuracy = (n_correct / len(results) * 100.0) if results else 0.0

        self.result_text.text = (
            "온라인 테스트 완료\n\n"
            f"SUCCESS : {n_success}/{len(results)}\n"
            f"FAIL : {n_fail}/{len(results)}\n"
            f"LEFT final decision : {left_final}\n"
            f"RIGHT final decision : {right_final}\n"
            f"Target accuracy : {n_correct}/{len(results)} ({accuracy:.1f}%)\n"
            f"Mean decision time (SUCCESS) : {mean_time_text}"
        )
        event.clearEvents(eventType="keyboard")
        self.result_text.draw()
        self.win.flip()
        wait_with_escape(FINAL_RESULT_DURATION)
        
    def show_initial_relax(self, duration: float, explore):
        """Show the initial RELAX screen immediately after the experiment starts."""
        event.clearEvents(eventType="keyboard")
        self.initial_relax_text.draw()
        self.win.callOnFlip(explore.set_marker, INITIAL_RELAX_ONSET)
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
        N_TRIALS,
        BLOCK_REST_INTERVAL,
        seed=args.seed,
    )

    model_path, bundle = load_bundle(subject, args.model_dir)
    runtime = BundleRuntime(bundle)

    window_samples = int(round(CLASSIFICATION_WINDOW * runtime.fs))
    output_dir, eeg_base, log_path = build_output_paths(args)

    if log_path.exists():
        raise FileExistsError(
            f"{log_path} already exists. Use a different -f name or add --timestamp."
        )

    print("=" * 78)
    print("DYNAMIC FADING MOTOR IMAGERY BCI TEST")
    print("=" * 78)
    print(f"Subject              : {subject}")
    print(f"Model                : {model_path}")
    print(f"Bundle schema        : {bundle['schema_version']}")
    print(f"Sampling rate        : {bundle['sampling_rate']} Hz")
    print(f"Channels             : {bundle['input']['selected_channels']}")
    print(
        "Model epoch          : "
        f"{bundle['epoch']['start_sec']}-{bundle['epoch']['end_sec']} s "
        f"({bundle['epoch']['n_samples']} samples)"
    )
    print(f"Classifier           : {bundle['metadata']['classifier']}")
    print(f"Trials               : {N_TRIALS} (6 blocks x 10; each block = 5 LEFT + 5 RIGHT)")
    print(f"Initial RELAX        : {INITIAL_RELAX_DURATION:.1f} s")
    print(f"Trial REST           : {TRIAL_REST_DURATION:.1f} s")
    print(
        f"Classification       : {CLASSIFICATION_WINDOW:.1f} s x "
        f"max {MAX_PREDICTIONS} non-overlapping windows"
    )
    print(f"Max decision time    : {MAX_CLASSIFICATION_DURATION:.1f} s")
    print(f"Target totals        : LEFT={target_schedule.count('LEFT')}, RIGHT={target_schedule.count('RIGHT')}")
    print(f"Random seed          : {args.seed}")
    for block_idx in range(N_TRIALS // BLOCK_REST_INTERVAL):
        block = target_schedule[
            block_idx * BLOCK_REST_INTERVAL : (block_idx + 1) * BLOCK_REST_INTERVAL
        ]
        print(f"  Block {block_idx + 1}: {' '.join(x[0] for x in block)}")
    print(f"Output folder        : {output_dir}")
    print("=" * 78)

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

    log_fields = [
        "subject",
        "trial",
        "target_direction",
        "prediction_sequence",
        "predicted_label_sequence",
        "right_probability_sequence",
        "selection_level_sequence",
        "candidate_sequence",
        "initial_candidate_decision",
        "candidate_decision",
        "final_decision",
        "is_correct",
        "final_selection_level",
        "n_predictions",
        "decision_time_s",
        "actual_wall_time_s",
        "status",
        "trial_rest_onset_s",
        "classification_onset_s",
        "classification_onset_stream_sample",
        "outcome_onset_s",
    ]

    try:
        runtime.reset()

        explore.connect(device_name=args.device_name)
        connected = True

        explore.stream_processor.subscribe(
            callback=runtime.process_packet,
            topic=TOPICS.raw_ExG,
        )
        subscribed = True

        explore.record_data(
            file_name=str(eeg_base),
            file_type="csv",
            do_overwrite=False,
        )
        recording = True

        # Wait briefly for live samples before allowing the experiment to begin.
        stream_ready_deadline = time.monotonic() + 3.0
        while runtime.sample_count == 0 and time.monotonic() < stream_ready_deadline:
            check_escape()
            core.wait(0.02)
        if runtime.sample_count == 0:
            raise RuntimeError("No live ExG packets were received from the Explore device.")

        with log_path.open("x", newline="", encoding="utf-8-sig") as log_file:
            writer = csv.DictWriter(log_file, fieldnames=log_fields)
            writer.writeheader()

            wait_for_space(ui.start_text, win)

            global_clock.reset()
            explore.set_marker(SESSION_START)

            # Initial 5-s RELAX before Trial 1. No classification occurs here.
            ui.show_initial_relax(INITIAL_RELAX_DURATION, explore)

            for trial_number in range(1, N_TRIALS + 1):
                target_direction = target_schedule[trial_number - 1]

                # 1) 1-s REST: common Level-0 circle, no EEG classification.
                trial_rest_onset = ui.show_trial_rest(
                    trial_number,
                    target_direction,
                    explore,
                    global_clock,
                )

                # 2) Classification starts from the same Level-0 screen.
                classification_onset, classification_start_sample = ui.begin_classification(
                    trial_number,
                    target_direction,
                    explore,
                    global_clock,
                    runtime,
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

                # 3) Exact, non-overlapping 0.5-s windows: 0-0.5, 0.5-1.0, ...
                for prediction_index in range(1, MAX_PREDICTIONS + 1):
                    window_start = (
                        classification_start_sample
                        + (prediction_index - 1) * window_samples
                    )
                    epoch = runtime.get_window_epoch(
                        window_start,
                        window_samples,
                        timeout=2.0,
                    )
                    predicted_label, predicted_direction, right_probability = runtime.predict(epoch)

                        
                    if predicted_direction not in {"LEFT", "RIGHT"}:
                        raise RuntimeError(
                            f"Classifier returned unexpected direction: {predicted_direction!r}"
                        )

                    # Prediction marker is emitted immediately after classification.
                    explore.set_marker(
                        PRED_LEFT_ONSET
                        if predicted_direction == "LEFT"
                        else PRED_RIGHT_ONSET
                    )

                    prediction_sequence.append(
                        "L" if predicted_direction == "LEFT" else "R"
                    )
                    predicted_label_sequence.append(str(predicted_label))
                    probability_sequence.append(
                        "" if right_probability is None else f"{right_probability:.8f}"
                    )

                    # Dynamic Fading rule from Chae et al. (2012):
                    #   Rule 1) Whenever Selection Level is 0, the next
                    #           classification becomes the NEW Candidate Decision.
                    #   Rule 2) Same as Candidate -> Level +1; otherwise -> Level -1.
                    # Therefore the Candidate is stable only while Level > 0.
                    # Once Level falls to 0, the next prediction may switch the
                    # feedback direction from LEFT to RIGHT or vice versa.
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

                    # Decision time is based on EEG covered, excluding the 1-s REST.
                    decision_time = prediction_index * CLASSIFICATION_WINDOW
                    actual_wall_time = global_clock.getTime() - classification_onset

                    # Reaching Level 4 on the 30th window (15.0 s) is still SUCCESS.
                    if selection_level == 4:
                        status = "SUCCESS"
                        final_decision = candidate
                        outcome_onset = ui.show_outcome(
                            trial_number,
                            candidate,
                            target_direction,
                            status,
                            explore,
                            global_clock,
                        )
                        break

                    # Level 0 hides the arrow. The current Candidate value is kept
                    # only as history; because Selection Level is 0, the NEXT
                    # prediction will overwrite it according to Rule 1.
                    ui.show_level(
                        trial_number,
                        selection_level,
                        candidate,
                        target_direction,
                        explore,
                        global_clock,
                    )

                # 4) No Level 4 after all 30 windows -> FAIL.
                if status is None:
                    status = "FAIL"
                    final_decision = None
                    decision_time = MAX_CLASSIFICATION_DURATION
                    actual_wall_time = global_clock.getTime() - classification_onset
                    outcome_onset = ui.show_outcome(
                        trial_number,
                        candidate,
                        target_direction,
                        status,
                        explore,
                        global_clock,
                    )

                is_correct = (
                    final_decision == target_direction
                    if final_decision in {"LEFT", "RIGHT"}
                    else False
                )

                row = {
                    "subject": subject,
                    "trial": trial_number,
                    "target_direction": target_direction,
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
                    f"Trial {trial_number:02d}/{N_TRIALS} | "
                    f"target={target_direction:<5} | "
                    f"candidate={(candidate or 'NONE'):<5} | "
                    f"final={(final_decision or 'NONE'):<5} | "
                    f"level={selection_level} | "
                    f"time={float(decision_time):>4.1f}s | "
                    f"status={status:<7} | "
                    f"correct={int(is_correct)} | "
                    f"pred={''.join(prediction_sequence)}"
                )
                
                # [추가] 10, 20, 30, 40, 50 Trial 종료 시 5초 휴식 (마지막 60 Trial 제외)
                if trial_number % BLOCK_REST_INTERVAL == 0 and trial_number < N_TRIALS:
                    print(f"\n>>> Block rest for {BLOCK_REST_DURATION:.0f} seconds...\n")
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
                explore.stream_processor.unsubscribe(
                    callback=runtime.process_packet,
                    topic=TOPICS.raw_ExG,
                )
            except Exception as exc:
                print(f"Could not unsubscribe raw ExG callback cleanly: {exc}")

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
            n_success = sum(row["status"] == "SUCCESS" for row in results)
            n_fail = sum(row["status"] == "FAIL" for row in results)
            n_correct = sum(int(row.get("is_correct", 0)) for row in results)
            print(
                f"Final result: SUCCESS={n_success}, FAIL={n_fail}, "
                f"TARGET_CORRECT={n_correct}/{len(results)}"
            )

    core.quit()


if __name__ == "__main__":
    main()
