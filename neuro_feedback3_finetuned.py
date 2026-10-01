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
from sklearn.metrics import balanced_accuracy_score, recall_score, roc_auc_score

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
N_TRIALS = 30
CALIBRATION_TRIALS = 20
CALIBRATION_BLOCK_SIZE = 10
CALIBRATION_MI_DURATION = 3.0
CALIBRATION_REST_DURATION = 1.0
CALIBRATION_BLOCK_REST_DURATION = 5.0
ORIGINAL_THRESHOLD_WEIGHT = 0.40
CALIBRATION_THRESHOLD_WEIGHT = 0.60

# Daily amplitude normalization. training_channel_scale must be exported in
# bundle["adaptation"] from OFFLINE 3.0-s MI epochs using the exact same stream
# preprocessing and robust scale calculation used here.  Online calibration uses
# the 20 x 3.0-s MI epochs to define today's robust amplitude range.
ENABLE_AMPLITUDE_NORMALIZATION = True
AMPLITUDE_MAD_TO_SIGMA = 1.4826
AMPLITUDE_RANGE_LOW_PERCENTILE = 10.0
AMPLITUDE_RANGE_HIGH_PERCENTILE = 90.0
AMPLITUDE_CURRENT_WINDOW = 1.0
AMPLITUDE_OUT_OF_RANGE_STREAK = 2
AMPLITUDE_GAIN_SMOOTHING_ALPHA = 0.20
AMPLITUDE_GAIN_MIN = 0.67
AMPLITUDE_GAIN_MAX = 1.50
AMPLITUDE_SCALE_EPS = 1e-12

# Only the final LDA/SVM head is eligible for daily adaptation.  The fitted
# CSP/Riemannian/filter-bank/scaler objects in the participant bundle stay fixed.
ENABLE_CLASSIFIER_FINETUNING = True
MIN_FINETUNED_AUC = 0.55
MIN_FINETUNED_AUC_GAIN = 0.02
MIN_FINETUNED_DIRECTION_RECALL = 0.40
EXPECTED_SAMPLING_RATE = 250.0
CLASSIFICATION_WINDOW = 0.5
INITIAL_RELAX_DURATION = 5.0
MAIN_RELAX_DURATION = 5.0
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
            "Participant id. It must match bundle['participant'] in the selected joblib."
        ),
    )
    parser.add_argument(
        "-m",
        "--model-file",
        required=True,
        help=(
            "Joblib filename or path to load, e.g. wmj_model.joblib or "
            "wmj_model_plus0929.joblib. If only a filename is given, the program "
            "searches --model-dir, <script_dir>/--model-dir, and <script_dir>."
        ),
    )
    parser.add_argument(
        "--model-dir",
        default="models",
        help=(
            "Directory searched when --model-file is a filename rather than a path. "
            "Default: models"
        ),
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
    For the current experiment: 30 trials -> 3 blocks of 10 -> 5 LEFT + 5 RIGHT per block.
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


def find_calibration_threshold(
    calibration_rows: list[dict],
    original_threshold: float,
) -> tuple[float, float]:
    """Choose the trial-level P(RIGHT) threshold with best balanced accuracy.

    Each calibration trial contributes exactly one score: the median P(RIGHT)
    across its non-overlapping 0.5-s motor-imagery windows.  If several
    thresholds give the same balanced accuracy, choose the one closest to the
    participant's original offline threshold.  This tie-break keeps the small
    20-trial calibration from moving the decision boundary unnecessarily.
    """
    if not calibration_rows:
        raise ValueError("Calibration rows are empty.")

    scores = np.asarray(
        [float(row["trial_score_right_probability"]) for row in calibration_rows],
        dtype=float,
    )
    targets = np.asarray(
        [1 if str(row["target_direction"]).upper() == "RIGHT" else 0 for row in calibration_rows],
        dtype=int,
    )

    if not np.isfinite(scores).all():
        raise ValueError("Calibration P(RIGHT) scores contain NaN or Inf.")
    if set(np.unique(targets)) != {0, 1}:
        raise ValueError("Calibration requires both LEFT and RIGHT trials.")

    unique_scores = np.unique(scores)
    midpoints = (unique_scores[:-1] + unique_scores[1:]) / 2.0
    candidates = np.unique(
        np.clip(
            np.concatenate(
                [
                    np.asarray([0.0, 1.0, float(original_threshold)]),
                    midpoints,
                ]
            ),
            0.0,
            1.0,
        )
    )

    best_threshold = float(original_threshold)
    best_balanced_accuracy = -np.inf
    best_distance = np.inf

    for threshold in candidates:
        predicted_right = scores >= float(threshold)
        right_mask = targets == 1
        left_mask = targets == 0

        sensitivity_right = float(np.mean(predicted_right[right_mask]))
        specificity_left = float(np.mean(~predicted_right[left_mask]))
        balanced_accuracy = 0.5 * (sensitivity_right + specificity_left)
        distance = abs(float(threshold) - float(original_threshold))

        if (
            balanced_accuracy > best_balanced_accuracy + 1e-12
            or (
                abs(balanced_accuracy - best_balanced_accuracy) <= 1e-12
                and distance < best_distance - 1e-12
            )
        ):
            best_threshold = float(threshold)
            best_balanced_accuracy = float(balanced_accuracy)
            best_distance = float(distance)

    return best_threshold, best_balanced_accuracy


def calibration_accuracy(calibration_rows: list[dict], threshold: float) -> float:
    """Return trial-level calibration accuracy for a supplied threshold."""
    if not calibration_rows:
        return float("nan")

    correct = 0
    for row in calibration_rows:
        score = float(row["trial_score_right_probability"])
        predicted = "RIGHT" if score >= float(threshold) else "LEFT"
        correct += int(predicted == str(row["target_direction"]).upper())
    return correct / len(calibration_rows)


# =============================================================================
# Bundle loading / validation
# =============================================================================
def resolve_model_path(model_file: str, model_dir: str) -> Path:
    """Resolve the exact joblib filename/path supplied on the command line."""
    requested = Path(model_file).expanduser()
    script_dir = Path(__file__).resolve().parent

    # If the user supplied a path (absolute or containing a directory), use that
    # path first.  A bare filename is searched in the usual model locations.
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
    resolved_candidates = []
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        resolved_candidates.append(candidate)
        if candidate.exists():
            if candidate.suffix.lower() != ".joblib":
                raise ValueError(
                    f"Selected model file is not a .joblib file: {candidate}"
                )
            return candidate

    searched = "\n  - ".join(str(p) for p in resolved_candidates)
    raise FileNotFoundError(
        f"Could not find the requested model file: {model_file!r}\n"
        f"Searched:\n  - {searched}"
    )


def load_bundle(subject: str, model_file: str, model_dir: str):
    model_path = resolve_model_path(model_file, model_dir)
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
            f"{model_path.name} is marked online_ready=False.\n"
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
        # One multiplicative gain per selected EEG channel. It remains identity
        # while the 20 calibration MI epochs are collected, then starts from the
        # offline-training / today-median ratio and can adapt slowly during the
        # main experiment when today's robust range is persistently exceeded.
        self.channel_gain = np.ones(len(self.selected_channels), dtype=np.float64)

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
            self.channel_gain = np.ones(len(self.selected_channels), dtype=np.float64)
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

    def get_processed_segment(
        self,
        start_sample: int,
        n_samples: int,
        timeout: float = 2.0,
    ) -> np.ndarray:
        """Return an arbitrary-length segment after bundle stream preprocessing.

        Shape is samples x channels for a single-band stream, or samples x bands
        x channels for a filter-bank stream. No daily gain is applied here.
        """
        start = int(start_sample)
        n_samples = int(n_samples)
        if n_samples <= 0:
            raise ValueError("n_samples must be positive.")
        stop = start + n_samples

        deadline = time.monotonic() + timeout
        with self._condition:
            while self._sample_count < stop:
                if self._stream_error is not None:
                    raise RuntimeError("EEG stream callback failed") from self._stream_error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Not enough EEG samples: have {self._sample_count}, need {stop}. "
                        "Check device streaming/sampling rate."
                    )
                self._condition.wait(timeout=min(0.05, remaining))
            segment = self._slice_samples_locked(start, stop)

        n_channels = len(self.selected_channels)
        if segment.ndim == 2 and segment.shape != (n_samples, n_channels):
            raise RuntimeError(
                f"Segment shape mismatch: got {segment.shape}, expected "
                f"({n_samples}, {n_channels})."
            )
        if segment.ndim == 3 and segment.shape[2] != n_channels:
            raise RuntimeError(
                f"Filter-bank segment channel mismatch: got {segment.shape}, "
                f"expected final axis {n_channels}."
            )
        if segment.ndim not in {2, 3}:
            raise RuntimeError(f"Unexpected segment dimensionality: {segment.shape}")
        return np.asarray(segment, dtype=np.float64)

    @staticmethod
    def robust_channel_scale(segment: np.ndarray) -> np.ndarray:
        """Return one robust amplitude scale per selected channel.

        scale = 1.4826 * MAD. For filter-bank streams, MAD is calculated across
        time in each band, then the median across bands gives one scale/channel.
        The offline MI-based training_channel_scale must use this exact rule.
        """
        x = np.asarray(segment, dtype=np.float64)
        if x.ndim == 2:  # samples x channels
            center = np.median(x, axis=0)
            mad = np.median(np.abs(x - center[None, :]), axis=0)
            scale = AMPLITUDE_MAD_TO_SIGMA * mad
        elif x.ndim == 3:  # samples x bands x channels
            center = np.median(x, axis=0)
            mad_per_band = np.median(np.abs(x - center[None, :, :]), axis=0)
            scale = AMPLITUDE_MAD_TO_SIGMA * np.median(mad_per_band, axis=0)
        else:
            raise ValueError(f"Unexpected amplitude-scale segment shape: {x.shape}")
        return np.asarray(scale, dtype=np.float64)

    def set_channel_gain(self, gain: np.ndarray) -> None:
        gain = np.asarray(gain, dtype=np.float64).reshape(-1)
        if gain.shape != (len(self.selected_channels),):
            raise ValueError(
                f"channel gain shape {gain.shape} does not match "
                f"{len(self.selected_channels)} selected channels."
            )
        if not np.isfinite(gain).all() or np.any(gain <= 0):
            raise ValueError("channel gain must contain finite positive values.")
        self.channel_gain = gain.copy()

    def apply_channel_gain(self, epoch: np.ndarray) -> np.ndarray:
        """Apply current daily channel gain to one or more model-shaped epochs."""
        x = np.asarray(epoch, dtype=np.float64)
        gain = np.asarray(self.channel_gain, dtype=np.float64)
        if x.ndim == 3:  # batch x channels x time
            if x.shape[1] != len(gain):
                raise ValueError(f"Epoch channel mismatch for gain: {x.shape}")
            return x * gain[None, :, None]
        if x.ndim == 4:  # batch x bands x channels x time
            if x.shape[2] != len(gain):
                raise ValueError(f"Filter-bank epoch channel mismatch for gain: {x.shape}")
            return x * gain[None, None, :, None]
        raise ValueError(f"Unexpected model epoch shape for gain: {x.shape}")

    def get_window_epoch(
        self,
        start_sample: int,
        n_samples: int,
        timeout: float = 2.0,
        apply_gain: bool = True,
    ) -> np.ndarray:
        """Return one exact non-overlapping model window from the stream."""
        n_samples = int(n_samples)
        expected_samples = int(self.epoch_spec["n_samples"])
        if n_samples != expected_samples:
            raise ValueError(
                f"Requested {n_samples} samples, but the model expects {expected_samples}."
            )

        segment = self.get_processed_segment(start_sample, n_samples, timeout=timeout)
        if segment.ndim == 2:
            epoch = segment.T[np.newaxis, :, :]
        else:
            epoch = np.transpose(segment, (1, 2, 0))[np.newaxis, :, :, :]

        if apply_gain:
            epoch = self.apply_channel_gain(epoch)
        return epoch

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

    def extract_frozen_features(self, epochs: np.ndarray) -> np.ndarray:
        """Transform epochs with the already-fitted feature extractor.

        This deliberately excludes the final LDA/SVM classifier.  No CSP,
        covariance reference, tangent-space mapping, or scaler is refitted.
        """
        kind = self.predictor["kind"]
        model = self.predictor["objects"]["model"]

        if kind == "sklearn_pipeline":
            if not hasattr(model, "steps") or len(model.steps) < 2:
                raise RuntimeError(
                    "Classifier fine-tuning requires a pipeline with at least "
                    "one fitted feature step and one final classifier."
                )
            frozen = model[:-1]
            return np.asarray(frozen.transform(epochs), dtype=np.float64)

        if kind == "hybrid_fbriemann_csp":
            features = self._hybrid_features(epochs)
            scaler = self.predictor["objects"].get("scaler")
            if scaler is not None:
                features = scaler.transform(features)
            return np.asarray(features, dtype=np.float64)

        raise NotImplementedError(f"Unsupported predictor kind: {kind}")

    def clone_classifier_head(self):
        """Return an unfitted clone of only the final participant classifier."""
        model = self.predictor["objects"]["model"]
        if self.predictor["kind"] == "sklearn_pipeline":
            return clone(model.steps[-1][1])
        if self.predictor["kind"] == "hybrid_fbriemann_csp":
            return clone(model)
        raise NotImplementedError(
            f"Unsupported predictor kind: {self.predictor['kind']}"
        )

    def install_classifier_head(self, fitted_head) -> None:
        """Install a validated daily head in memory; never modify the joblib file."""
        if self.predictor["kind"] == "sklearn_pipeline":
            model = self.predictor["objects"]["model"]
            final_name = model.steps[-1][0]
            model.steps[-1] = (final_name, fitted_head)
            return
        if self.predictor["kind"] == "hybrid_fbriemann_csp":
            self.predictor["objects"]["model"] = fitted_head
            return
        raise NotImplementedError(
            f"Unsupported predictor kind: {self.predictor['kind']}"
        )

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


def _load_training_channel_scale(bundle: dict, selected_channels: list[str]) -> np.ndarray:
    """Load the offline amplitude reference stored in bundle['adaptation']."""
    adaptation = bundle.get("adaptation", {})
    value = adaptation.get("training_channel_scale")
    if value is None:
        raise RuntimeError(
            "Amplitude normalization is enabled, but the model bundle has no "
            "bundle['adaptation']['training_channel_scale']. Regenerate the offline "
            "joblib using 3.0-s MI epochs and the same preprocessing/MAD rule."
        )

    if isinstance(value, dict):
        missing = [ch for ch in selected_channels if ch not in value]
        if missing:
            raise RuntimeError(
                "training_channel_scale is missing selected channels: " + ", ".join(missing)
            )
        scale = np.asarray([value[ch] for ch in selected_channels], dtype=np.float64)
    else:
        scale = np.asarray(value, dtype=np.float64).reshape(-1)

    if scale.shape != (len(selected_channels),):
        raise RuntimeError(
            f"training_channel_scale has shape {scale.shape}; expected "
            f"({len(selected_channels)},) for channels {selected_channels}."
        )
    if not np.isfinite(scale).all() or np.any(scale <= AMPLITUDE_SCALE_EPS):
        raise RuntimeError("training_channel_scale must contain finite positive values.")
    return scale


def compute_daily_amplitude_normalization(
    runtime: BundleRuntime,
    calibration_mi_segments: list[np.ndarray],
) -> dict:
    """Build today's robust MI-amplitude profile and the initial channel gain.

    Each of the 20 calibration trials contributes one 3.0-s MI amplitude scale
    per channel using the same 1.4826*MAD rule as the offline training reference.
    Today's normal range is the 10th-90th percentile across those 20 scales.
    The initial gain aligns today's median MI amplitude to the offline MI median.
    """
    training_scale = _load_training_channel_scale(runtime.bundle, runtime.selected_channels)
    if len(calibration_mi_segments) != CALIBRATION_TRIALS:
        raise RuntimeError(
            f"Expected {CALIBRATION_TRIALS} calibration MI segments, got "
            f"{len(calibration_mi_segments)}."
        )

    mi_scales = np.vstack(
        [runtime.robust_channel_scale(segment) for segment in calibration_mi_segments]
    )
    expected_shape = (CALIBRATION_TRIALS, len(runtime.selected_channels))
    if mi_scales.shape != expected_shape:
        raise RuntimeError(
            f"Unexpected calibration MI scale matrix shape: {mi_scales.shape}; "
            f"expected {expected_shape}."
        )
    if not np.isfinite(mi_scales).all() or np.any(mi_scales <= AMPLITUDE_SCALE_EPS):
        raise RuntimeError(
            "Calibration MI amplitude scales contain zero/invalid values; check "
            "electrode contact and preprocessing."
        )

    today_lower = np.percentile(
        mi_scales, AMPLITUDE_RANGE_LOW_PERCENTILE, axis=0
    )
    today_median = np.median(mi_scales, axis=0)
    today_upper = np.percentile(
        mi_scales, AMPLITUDE_RANGE_HIGH_PERCENTILE, axis=0
    )

    if (
        not np.isfinite(today_lower).all()
        or not np.isfinite(today_median).all()
        or not np.isfinite(today_upper).all()
        or np.any(today_lower <= AMPLITUDE_SCALE_EPS)
        or np.any(today_median <= AMPLITUDE_SCALE_EPS)
        or np.any(today_upper <= AMPLITUDE_SCALE_EPS)
    ):
        raise RuntimeError("Today's robust MI amplitude range contains invalid values.")

    raw_gain = training_scale / today_median
    clipped_gain = np.clip(raw_gain, AMPLITUDE_GAIN_MIN, AMPLITUDE_GAIN_MAX)
    runtime.set_channel_gain(clipped_gain)
    return {
        "training_scale": training_scale,
        "today_lower": today_lower,
        "today_median": today_median,
        "today_upper": today_upper,
        "raw_gain": raw_gain,
        "applied_gain": clipped_gain.copy(),
        "mi_scales": mi_scales,
    }


def update_realtime_amplitude_gain(
    runtime: BundleRuntime,
    current_segment: np.ndarray,
    amplitude_profile: dict,
    out_of_range_streak: np.ndarray,
) -> dict:
    """Adapt gain outside the robust range and recover it inside the range.

    current_segment is the most recent 1.0-s *pre-gain* EEG segment. A channel
    must be outside today's robust calibration range for two consecutive checks
    before its target gain is updated. When the channel returns to the normal
    range, its gain is smoothly pulled back toward the calibration initial_gain.
    Both directions use alpha=0.20 to avoid abrupt scale jumps.
    """
    current_scale = runtime.robust_channel_scale(current_segment)
    lower = np.asarray(amplitude_profile["today_lower"], dtype=np.float64)
    upper = np.asarray(amplitude_profile["today_upper"], dtype=np.float64)
    training_scale = np.asarray(amplitude_profile["training_scale"], dtype=np.float64)
    initial_gain = np.asarray(amplitude_profile["applied_gain"], dtype=np.float64)

    if current_scale.shape != lower.shape:
        raise RuntimeError(
            f"Current amplitude scale shape {current_scale.shape} does not match "
            f"calibration range shape {lower.shape}."
        )
    if initial_gain.shape != lower.shape:
        raise RuntimeError(
            f"Initial gain shape {initial_gain.shape} does not match "
            f"calibration range shape {lower.shape}."
        )

    outside = (current_scale < lower) | (current_scale > upper)
    inside = ~outside
    out_of_range_streak = np.where(outside, out_of_range_streak + 1, 0).astype(int)
    eligible = out_of_range_streak >= AMPLITUDE_OUT_OF_RANGE_STREAK

    old_gain = np.asarray(runtime.channel_gain, dtype=np.float64).copy()
    raw_target_gain = training_scale / np.maximum(current_scale, AMPLITUDE_SCALE_EPS)
    clipped_target_gain = np.clip(
        raw_target_gain, AMPLITUDE_GAIN_MIN, AMPLITUDE_GAIN_MAX
    )

    alpha = float(AMPLITUDE_GAIN_SMOOTHING_ALPHA)
    new_gain = old_gain.copy()

    # If amplitude is back inside today's normal range, do not leave a temporary
    # correction fixed in place. Slowly recover toward the calibration initial_gain.
    if np.any(inside):
        recovered = (1.0 - alpha) * old_gain + alpha * initial_gain
        new_gain[inside] = recovered[inside]

    # If amplitude remains outside the normal range for the required streak,
    # keep the existing realtime correction toward the current target gain.
    if np.any(eligible):
        corrected = (1.0 - alpha) * old_gain + alpha * clipped_target_gain
        new_gain[eligible] = corrected[eligible]

    if np.any(inside) or np.any(eligible):
        new_gain = np.clip(new_gain, AMPLITUDE_GAIN_MIN, AMPLITUDE_GAIN_MAX)
        runtime.set_channel_gain(new_gain)

    return {
        "current_scale": current_scale,
        "outside": outside,
        "eligible": eligible,
        "out_of_range_streak": out_of_range_streak,
        "raw_target_gain": raw_target_gain,
        "clipped_target_gain": clipped_target_gain,
        "old_gain": old_gain,
        "applied_gain": np.asarray(runtime.channel_gain, dtype=np.float64).copy(),
    }


def _csv_vector(values: np.ndarray) -> str:
    return ",".join(f"{float(v):.10g}" for v in np.asarray(values).reshape(-1))


def _right_probabilities(estimator, features: np.ndarray, right_label) -> np.ndarray:
    probabilities = np.asarray(estimator.predict_proba(features), dtype=float)
    classes = np.asarray(estimator.classes_)
    matches = np.flatnonzero(classes == right_label)
    if len(matches) != 1:
        raise RuntimeError(
            f"Could not locate right label {right_label!r} in classes {classes}."
        )
    return probabilities[:, int(matches[0])]


def _trial_medians(
    window_probabilities: np.ndarray,
    trial_ids: np.ndarray,
    ordered_trial_ids: list[int],
) -> np.ndarray:
    return np.asarray(
        [
            float(np.median(window_probabilities[trial_ids == trial_id]))
            for trial_id in ordered_trial_ids
        ],
        dtype=float,
    )


def _score_trial_probabilities(
    scores: np.ndarray,
    targets: np.ndarray,
    reference_threshold: float,
) -> dict:
    rows = [
        {
            "target_direction": "RIGHT" if target else "LEFT",
            "trial_score_right_probability": float(score),
        }
        for score, target in zip(scores, targets)
    ]
    threshold, balanced_accuracy = find_calibration_threshold(
        rows, reference_threshold
    )
    predictions = (scores >= threshold).astype(int)
    recalls = recall_score(
        targets,
        predictions,
        labels=[0, 1],
        average=None,
        zero_division=0,
    )
    return {
        "auc": float(roc_auc_score(targets, scores)),
        "threshold": float(threshold),
        "balanced_accuracy": float(balanced_accuracy_score(targets, predictions)),
        "left_recall": float(recalls[0]),
        "right_recall": float(recalls[1]),
    }


def attempt_daily_classifier_finetuning(
    runtime: BundleRuntime,
    calibration_epochs: list[np.ndarray],
    calibration_window_targets: list[object],
    calibration_window_trial_ids: list[int],
    calibration_rows: list[dict],
    original_threshold: float,
) -> dict:
    """Try a head-only daily update and return an auditable decision.

    The first ten trials and last ten trials form two held-out folds.  All six
    windows belonging to one trial therefore stay together.  A candidate is
    installed only after its out-of-fold trial scores pass every safety gate.
    """
    result = {
        "applied": False,
        "reason": "disabled",
        "baseline": None,
        "candidate": None,
        "threshold_rows": calibration_rows,
    }
    if not ENABLE_CLASSIFIER_FINETUNING:
        return result

    try:
        epochs = np.concatenate(calibration_epochs, axis=0)
        features = runtime.extract_frozen_features(epochs)
        labels = np.asarray(calibration_window_targets)
        trial_ids = np.asarray(calibration_window_trial_ids, dtype=int)
        ordered_trials = list(range(1, CALIBRATION_TRIALS + 1))
        trial_targets = np.asarray(
            [
                1 if str(row["target_direction"]).upper() == "RIGHT" else 0
                for row in calibration_rows
            ],
            dtype=int,
        )
        baseline_scores = np.asarray(
            [float(row["trial_score_right_probability"]) for row in calibration_rows],
            dtype=float,
        )
        result["baseline"] = _score_trial_probabilities(
            baseline_scores, trial_targets, original_threshold
        )

        left_label = runtime.output_spec["left_label"]
        right_label = runtime.output_spec["right_label"]
        expected_labels = {left_label, right_label}
        if set(np.unique(labels)) != expected_labels:
            raise RuntimeError(
                f"Calibration labels {set(np.unique(labels))} do not match "
                f"model labels {expected_labels}."
            )

        oof_window_probabilities = np.full(len(labels), np.nan, dtype=float)
        # Calibration is block-balanced: trials 1-10 and 11-20 each contain 5L/5R.
        for test_first_block in (True, False):
            test_mask = trial_ids <= CALIBRATION_BLOCK_SIZE
            if not test_first_block:
                test_mask = ~test_mask
            train_mask = ~test_mask
            head = runtime.clone_classifier_head()
            head.fit(features[train_mask], labels[train_mask])
            oof_window_probabilities[test_mask] = _right_probabilities(
                head, features[test_mask], right_label
            )

        if not np.isfinite(oof_window_probabilities).all():
            raise RuntimeError("Daily classifier OOF probabilities are incomplete.")

        candidate_scores = _trial_medians(
            oof_window_probabilities, trial_ids, ordered_trials
        )
        candidate_metrics = _score_trial_probabilities(
            candidate_scores, trial_targets, original_threshold
        )
        result["candidate"] = candidate_metrics

        baseline_auc = result["baseline"]["auc"]
        reasons = []
        if candidate_metrics["auc"] < MIN_FINETUNED_AUC:
            reasons.append(
                f"AUC {candidate_metrics['auc']:.3f} < {MIN_FINETUNED_AUC:.3f}"
            )
        if candidate_metrics["auc"] < baseline_auc + MIN_FINETUNED_AUC_GAIN:
            reasons.append(
                f"AUC gain {candidate_metrics['auc'] - baseline_auc:+.3f} "
                f"< {MIN_FINETUNED_AUC_GAIN:.3f}"
            )
        if candidate_metrics["left_recall"] < MIN_FINETUNED_DIRECTION_RECALL:
            reasons.append(
                f"LEFT recall {candidate_metrics['left_recall']:.3f} "
                f"< {MIN_FINETUNED_DIRECTION_RECALL:.3f}"
            )
        if candidate_metrics["right_recall"] < MIN_FINETUNED_DIRECTION_RECALL:
            reasons.append(
                f"RIGHT recall {candidate_metrics['right_recall']:.3f} "
                f"< {MIN_FINETUNED_DIRECTION_RECALL:.3f}"
            )

        if reasons:
            result["reason"] = "; ".join(reasons)
            return result

        final_head = runtime.clone_classifier_head()
        final_head.fit(features, labels)
        runtime.install_classifier_head(final_head)
        result["applied"] = True
        result["reason"] = "passed two-block OOF AUC and direction-recall gates"
        result["threshold_rows"] = [
            {
                **row,
                "trial_score_right_probability": float(score),
            }
            for row, score in zip(calibration_rows, candidate_scores)
        ]
        return result
    except Exception as exc:
        # A failed adaptation must never prevent use of the original model.
        result["reason"] = f"fine-tuning error; original model kept: {exc}"
        return result


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
                "Session-Calibrated Dynamic Fading Motor Imagery BCI Test\n\n"
                "먼저 20 trials (LEFT 10 / RIGHT 10) calibration을 수행합니다.\n"
                "Calibration에서는 제시된 방향의 손 움직임을 3초 동안 상상하세요.\n"
                "Calibration MI 3초로 진폭 범위를 설정한 후 분류기 파인튜닝과 오늘의 threshold를 계산합니다.\n"
                "검증을 통과하지 못하면 원래 분류기를 그대로 사용합니다.\n"
                "본 실험에서는 중앙 cue의 색상 변화가 실시간 분류 결과를 반영합니다.\n\n"
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
        """1-s visual REST before calibration MI; not used for amplitude scaling."""
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
        original_threshold: float,
        calibration_threshold: float,
        applied_threshold: float,
        calibration_balanced_accuracy: float,
        finetuning_applied: bool,
    ):
        model_status = "오늘 분류기 적용 (파인튜닝)" if finetuning_applied else "원래 분류기 유지 (베이스라인)"
        if finetuning_applied:
            applied_line = f"Applied threshold (Fixed) : {applied_threshold:.4f} (0.5000 고정)\n"
        else:
            applied_line = f"Applied threshold (40:60) : {applied_threshold:.4f}\n"

        self.calibration_summary_text.text = (
            "파인튜닝 및 Calibration 완료\n\n"
            f"Model : {model_status}\n"
            f"Original threshold : {original_threshold:.4f}\n"
            f"Calibration threshold : {calibration_threshold:.4f}\n"
            f"{applied_line}"
            f"Calibration balanced accuracy : {calibration_balanced_accuracy * 100.0:.1f}%\n\n"
            "SPACE : 30-trial 본 실험 시작\n"
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
    calibration_seed = None if args.seed is None else args.seed + 100003
    calibration_schedule = make_balanced_target_schedule(
        CALIBRATION_TRIALS,
        CALIBRATION_BLOCK_SIZE,
        seed=calibration_seed,
    )

    model_path, bundle = load_bundle(subject, args.model_file, args.model_dir)
    runtime = BundleRuntime(bundle)

    if runtime.predictor.get("decision_mode") != "predict_proba_threshold":
        raise RuntimeError(
            "20-trial threshold calibration requires predictor.decision_mode="
            "'predict_proba_threshold' so that P(RIGHT) is available."
        )
    if "threshold" not in runtime.predictor:
        raise RuntimeError("The model bundle does not contain predictor['threshold'].")

    if not np.isclose(
        ORIGINAL_THRESHOLD_WEIGHT + CALIBRATION_THRESHOLD_WEIGHT,
        1.0,
        atol=1e-12,
    ):
        raise ValueError(
            "ORIGINAL_THRESHOLD_WEIGHT + CALIBRATION_THRESHOLD_WEIGHT must equal 1.0."
        )

    original_threshold = float(runtime.predictor["threshold"])
    window_samples = int(round(CLASSIFICATION_WINDOW * runtime.fs))
    amplitude_window_samples = int(round(AMPLITUDE_CURRENT_WINDOW * runtime.fs))
    calibration_predictions = int(round(CALIBRATION_MI_DURATION / CLASSIFICATION_WINDOW))
    if calibration_predictions <= 0:
        raise ValueError("CALIBRATION_MI_DURATION must include at least one model window.")

    (
        output_dir,
        eeg_base,
        log_path,
        calibration_log_path,
        calibration_summary_path,
    ) = build_output_paths(args)

    for path_to_check in (log_path, calibration_log_path, calibration_summary_path):
        if path_to_check.exists():
            raise FileExistsError(
                f"{path_to_check} already exists. Use a different -f name or add --timestamp."
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
    print(f"Original threshold   : {original_threshold:.6f}")
    print(
        f"Calibration          : {CALIBRATION_TRIALS} trials "
        f"(2 blocks x {CALIBRATION_BLOCK_SIZE}; each block = 5 LEFT + 5 RIGHT)"
    )
    print(
        f"Calibration MI       : {CALIBRATION_MI_DURATION:.1f} s "
        f"({calibration_predictions} x {CLASSIFICATION_WINDOW:.1f}-s windows; median P(RIGHT))"
    )
    print(
        f"Threshold weighting  : old={ORIGINAL_THRESHOLD_WEIGHT:.2f}, "
        f"calibration={CALIBRATION_THRESHOLD_WEIGHT:.2f}"
    )
    print(
        "Amplitude norm       : "
        + (
            f"MI {CALIBRATION_MI_DURATION:.1f} s x {CALIBRATION_TRIALS}; "
            f"1.4826*MAD -> P{AMPLITUDE_RANGE_LOW_PERCENTILE:.0f}/median/"
            f"P{AMPLITUDE_RANGE_HIGH_PERCENTILE:.0f}; realtime {AMPLITUDE_CURRENT_WINDOW:.1f}-s "
            f"tracking; streak={AMPLITUDE_OUT_OF_RANGE_STREAK}; "
            f"alpha={AMPLITUDE_GAIN_SMOOTHING_ALPHA:.2f}; "
            f"gain clip [{AMPLITUDE_GAIN_MIN:.2f}, {AMPLITUDE_GAIN_MAX:.2f}]"
            if ENABLE_AMPLITUDE_NORMALIZATION
            else "disabled"
        )
    )
    n_main_blocks = N_TRIALS // BLOCK_REST_INTERVAL
    print(
        f"Main trials          : {N_TRIALS} "
        f"({n_main_blocks} blocks x {BLOCK_REST_INTERVAL}; "
        f"each block = {BLOCK_REST_INTERVAL // 2} LEFT + {BLOCK_REST_INTERVAL // 2} RIGHT)"
    )
    print(f"Initial RELAX        : {INITIAL_RELAX_DURATION:.1f} s")
    print(f"Main RELAX           : {MAIN_RELAX_DURATION:.1f} s")
    print(f"Trial REST           : {TRIAL_REST_DURATION:.1f} s")
    print(
        f"Classification       : {CLASSIFICATION_WINDOW:.1f} s x "
        f"max {MAX_PREDICTIONS} non-overlapping windows"
    )
    print(f"Max decision time    : {MAX_CLASSIFICATION_DURATION:.1f} s")
    print(
        f"Calibration totals   : LEFT={calibration_schedule.count('LEFT')}, "
        f"RIGHT={calibration_schedule.count('RIGHT')}"
    )
    for block_idx in range(CALIBRATION_TRIALS // CALIBRATION_BLOCK_SIZE):
        block = calibration_schedule[
            block_idx * CALIBRATION_BLOCK_SIZE : (block_idx + 1) * CALIBRATION_BLOCK_SIZE
        ]
        print(f"  Calibration block {block_idx + 1}: {' '.join(x[0] for x in block)}")
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
    calibration_rows = []
    calibration_epochs = []  # stored without daily gain until all 20 MI segments are available
    calibration_window_targets = []
    calibration_window_trial_ids = []
    calibration_mi_segments = []
    calibration_trial_metadata = []
    amplitude_result = None
    calibration_threshold = float("nan")
    applied_threshold = original_threshold
    finetuning_result = {
        "applied": False,
        "reason": "not attempted",
        "baseline": None,
        "candidate": None,
        "threshold_rows": calibration_rows,
    }

    calibration_log_fields = [
        "subject",
        "trial",
        "target_direction",
        "right_probability_sequence",
        "trial_score_right_probability",
        "prediction_at_original_threshold",
        "correct_at_original_threshold",
        "calibration_rest_onset_s",
        "calibration_rest_stream_sample",
        "calibration_cue_onset_s",
        "calibration_cue_stream_sample",
        "calibration_mi_channel_scale",
    ]

    log_fields = [
        "subject",
        "trial",
        "target_direction",
        "original_threshold",
        "calibration_threshold",
        "applied_threshold",
        "finetuning_applied",
        "finetuning_reason",
        "amplitude_normalization_enabled",
        "applied_channel_gain",
        "amplitude_current_scale_sequence",
        "amplitude_outside_range_sequence",
        "amplitude_update_eligible_sequence",
        "amplitude_raw_target_gain_sequence",
        "amplitude_applied_gain_sequence",
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

        with (
            calibration_log_path.open("x", newline="", encoding="utf-8-sig") as calibration_log_file,
            log_path.open("x", newline="", encoding="utf-8-sig") as log_file,
        ):
            calibration_writer = csv.DictWriter(
                calibration_log_file,
                fieldnames=calibration_log_fields,
            )
            calibration_writer.writeheader()
            writer = csv.DictWriter(log_file, fieldnames=log_fields)
            writer.writeheader()

            wait_for_space(ui.start_text, win)

            global_clock.reset()
            explore.set_marker(SESSION_START)

            # Initial 5-s RELAX before the 20-trial calibration.
            ui.show_initial_relax(INITIAL_RELAX_DURATION, explore)

            # =================================================================
            # Session calibration: 20 trials = 10 LEFT + 10 RIGHT
            # =================================================================
            explore.set_marker(CALIBRATION_START)
            print("\n" + "=" * 78)
            print("20-TRIAL SESSION CALIBRATION")
            print("=" * 78)

            mi_samples = int(round(CALIBRATION_MI_DURATION * runtime.fs))

            # Phase A: collect all 20 x 3.0-s MI segments and all 0.5-s MI windows
            # WITHOUT daily amplitude gain. The amplitude profile is computed only
            # after all 20 MI trials are available.
            for calibration_trial in range(1, CALIBRATION_TRIALS + 1):
                target_direction = calibration_schedule[calibration_trial - 1]

                calibration_rest_onset, calibration_rest_start_sample = ui.show_calibration_rest(
                    calibration_trial, explore, global_clock, runtime
                )

                calibration_cue_onset, calibration_start_sample = ui.begin_calibration_trial(
                    calibration_trial, target_direction, explore, global_clock, runtime
                )

                for prediction_index in range(calibration_predictions):
                    window_start = calibration_start_sample + prediction_index * window_samples
                    epoch = runtime.get_window_epoch(
                        window_start, window_samples, timeout=2.0, apply_gain=False
                    )
                    calibration_epochs.append(np.array(epoch, copy=True))
                    calibration_window_targets.append(
                        runtime.output_spec["right_label"]
                        if target_direction == "RIGHT"
                        else runtime.output_spec["left_label"]
                    )
                    calibration_window_trial_ids.append(calibration_trial)

                # All six 0.5-s windows have now arrived, so the exact 3.0-s MI
                # segment can be recovered in the same pre-gain signal domain.
                mi_segment = runtime.get_processed_segment(
                    calibration_start_sample, mi_samples, timeout=2.0
                )
                calibration_mi_segments.append(np.array(mi_segment, copy=True))

                calibration_trial_metadata.append({
                    "subject": subject,
                    "trial": calibration_trial,
                    "target_direction": target_direction,
                    "calibration_rest_onset_s": calibration_rest_onset,
                    "calibration_rest_stream_sample": calibration_rest_start_sample,
                    "calibration_cue_onset_s": calibration_cue_onset,
                    "calibration_cue_stream_sample": calibration_start_sample,
                })

                print(
                    f"Calibration {calibration_trial:02d}/{CALIBRATION_TRIALS} | "
                    f"target={target_direction:<5} | 3.0-s MI collected"
                )

                if (
                    calibration_trial % CALIBRATION_BLOCK_SIZE == 0
                    and calibration_trial < CALIBRATION_TRIALS
                ):
                    ui.show_calibration_block_rest(CALIBRATION_BLOCK_REST_DURATION, explore)

            # Phase B: 3.0-s MI x 20 -> channel MAD scales -> robust P10/P90 range.
            # Initial gain aligns today's MI median to the offline MI training scale.
            if ENABLE_AMPLITUDE_NORMALIZATION:
                amplitude_result = compute_daily_amplitude_normalization(
                    runtime, calibration_mi_segments
                )
            else:
                unity = np.ones(len(runtime.selected_channels), dtype=float)
                runtime.set_channel_gain(unity)
                nan_vec = np.full_like(unity, np.nan)
                amplitude_result = {
                    "training_scale": nan_vec.copy(),
                    "today_lower": nan_vec.copy(),
                    "today_median": nan_vec.copy(),
                    "today_upper": nan_vec.copy(),
                    "raw_gain": unity.copy(),
                    "applied_gain": unity.copy(),
                    "mi_scales": np.full(
                        (CALIBRATION_TRIALS, len(unity)), np.nan, dtype=float
                    ),
                }

            print("\nDAILY AMPLITUDE NORMALIZATION")
            for ch, tr, lo, med, hi, raw, applied in zip(
                runtime.selected_channels,
                amplitude_result["training_scale"],
                amplitude_result["today_lower"],
                amplitude_result["today_median"],
                amplitude_result["today_upper"],
                amplitude_result["raw_gain"],
                amplitude_result["applied_gain"],
            ):
                print(
                    f"  {ch:<6} training={tr:.6g}  today=P{AMPLITUDE_RANGE_LOW_PERCENTILE:.0f} "
                    f"{lo:.6g} / median {med:.6g} / P{AMPLITUDE_RANGE_HIGH_PERCENTILE:.0f} "
                    f"{hi:.6g}  raw_gain={raw:.4f}  initial_gain={applied:.4f}"
                )

            # Phase C: normalize stored calibration MI once, then recompute the
            # original classifier's P(RIGHT). Fine-tuning and T_cal therefore use
            # exactly the same normalized signal domain as the main experiment.
            calibration_epochs = [
                runtime.apply_channel_gain(epoch) for epoch in calibration_epochs
            ]
            normalized_window_probabilities = []
            for epoch in calibration_epochs:
                _, _, right_probability = runtime.predict(epoch)
                if right_probability is None:
                    raise RuntimeError(
                        "Calibration requires P(RIGHT), but runtime.predict() returned None."
                    )
                normalized_window_probabilities.append(float(right_probability))

            calibration_rows.clear()
            trial_ids_array = np.asarray(calibration_window_trial_ids, dtype=int)
            normalized_window_probabilities = np.asarray(
                normalized_window_probabilities, dtype=float
            )
            for meta in calibration_trial_metadata:
                trial_id = int(meta["trial"])
                probability_values = normalized_window_probabilities[
                    trial_ids_array == trial_id
                ]
                trial_score = float(np.median(probability_values))
                target_direction = str(meta["target_direction"]).upper()
                prediction_at_original = (
                    "RIGHT" if trial_score >= original_threshold else "LEFT"
                )
                correct_at_original = int(prediction_at_original == target_direction)

                calibration_row = {
                    "subject": subject,
                    "trial": trial_id,
                    "target_direction": target_direction,
                    "right_probability_sequence": ",".join(
                        f"{value:.8f}" for value in probability_values
                    ),
                    "trial_score_right_probability": f"{trial_score:.8f}",
                    "prediction_at_original_threshold": prediction_at_original,
                    "correct_at_original_threshold": correct_at_original,
                    "calibration_rest_onset_s": f"{meta['calibration_rest_onset_s']:.6f}",
                    "calibration_rest_stream_sample": int(
                        meta["calibration_rest_stream_sample"]
                    ),
                    "calibration_cue_onset_s": f"{meta['calibration_cue_onset_s']:.6f}",
                    "calibration_cue_stream_sample": int(
                        meta["calibration_cue_stream_sample"]
                    ),
                    "calibration_mi_channel_scale": _csv_vector(
                        amplitude_result["mi_scales"][trial_id - 1]
                    ),
                }
                calibration_rows.append(calibration_row)
                calibration_writer.writerow(calibration_row)
                print(
                    f"Normalized calibration {trial_id:02d}/{CALIBRATION_TRIALS} | "
                    f"target={target_direction:<5} | median P(RIGHT)={trial_score:.4f} | "
                    f"old-pred={prediction_at_original:<5} | correct={correct_at_original}"
                )
            calibration_log_file.flush()

            explore.set_marker(CALIBRATION_END)

            print("\nFINE-TUNING FINAL CLASSIFIER HEAD...")
            ui.show_finetuning()
            finetuning_result = attempt_daily_classifier_finetuning(
                runtime=runtime,
                calibration_epochs=calibration_epochs,
                calibration_window_targets=calibration_window_targets,
                calibration_window_trial_ids=calibration_window_trial_ids,
                calibration_rows=calibration_rows,
                original_threshold=original_threshold,
            )
            threshold_rows = finetuning_result["threshold_rows"]

            calibration_threshold, calibration_balanced_accuracy = find_calibration_threshold(
                threshold_rows,
                original_threshold,
            )

            # 조교 피드백 반영:
            # 1) 파인튜닝(새 모델) 채택 시: 모델 가중치가 오늘 데이터에 맞춰 재학습되었으므로
            #    이중 과적합(Double Overfitting)을 방지하기 위해 threshold는 0.5000으로 고정!
            # 2) 기존 모델 유지 시: 모델 가중치를 변경하지 못했으므로,
            #    세션 간 DC 드리프트 보정을 위해 4:6 threshold 보정을 적용.
            if finetuning_result["applied"]:
                applied_threshold = 0.50
            else:
                applied_threshold = float(
                    np.clip(
                        ORIGINAL_THRESHOLD_WEIGHT * original_threshold
                        + CALIBRATION_THRESHOLD_WEIGHT * calibration_threshold,
                        0.0,
                        1.0,
                    )
                )

            # IMPORTANT: only the in-memory runtime threshold is changed.
            # The original participant .joblib file is never overwritten.
            runtime.predictor["threshold"] = applied_threshold

            original_calibration_accuracy = calibration_accuracy(
                threshold_rows,
                original_threshold,
            )
            applied_calibration_accuracy = calibration_accuracy(
                threshold_rows,
                applied_threshold,
            )

            with calibration_summary_path.open(
                "x", newline="", encoding="utf-8-sig"
            ) as summary_file:
                summary_fields = [
                    "subject",
                    "n_calibration_trials",
                    "left_trials",
                    "right_trials",
                    "trial_score_method",
                    "threshold_selection_method",
                    "calibration_mi_duration_s",
                    "windows_per_calibration_trial",
                    "calibration_seed",
                    "amplitude_normalization_enabled",
                    "amplitude_scale_method",
                    "amplitude_scale_domain",
                    "amplitude_channel_names",
                    "training_channel_scale",
                    "today_channel_lower",
                    "today_channel_median",
                    "today_channel_upper",
                    "initial_raw_channel_gain",
                    "initial_applied_channel_gain",
                    "amplitude_range_low_percentile",
                    "amplitude_range_high_percentile",
                    "amplitude_current_window_s",
                    "amplitude_out_of_range_streak",
                    "amplitude_gain_smoothing_alpha",
                    "amplitude_gain_min",
                    "amplitude_gain_max",
                    "original_threshold",
                    "calibration_threshold",
                    "original_weight",
                    "calibration_weight",
                    "applied_threshold",
                    "best_calibration_balanced_accuracy",
                    "accuracy_at_original_threshold",
                    "accuracy_at_applied_threshold",
                    "finetuning_applied",
                    "finetuning_reason",
                    "baseline_auc",
                    "finetuned_oof_auc",
                    "finetuned_oof_balanced_accuracy",
                    "finetuned_oof_left_recall",
                    "finetuned_oof_right_recall",
                ]
                summary_writer = csv.DictWriter(summary_file, fieldnames=summary_fields)
                summary_writer.writeheader()
                summary_writer.writerow(
                    {
                        "subject": subject,
                        "n_calibration_trials": CALIBRATION_TRIALS,
                        "left_trials": calibration_schedule.count("LEFT"),
                        "right_trials": calibration_schedule.count("RIGHT"),
                        "trial_score_method": "median P(RIGHT) across 0.5-s windows",
                        "threshold_selection_method": (
                            "max balanced accuracy; tie -> closest to original threshold"
                        ),
                        "calibration_mi_duration_s": f"{CALIBRATION_MI_DURATION:.3f}",
                        "windows_per_calibration_trial": calibration_predictions,
                        "calibration_seed": "" if calibration_seed is None else calibration_seed,
                        "amplitude_normalization_enabled": int(ENABLE_AMPLITUDE_NORMALIZATION),
                        "amplitude_scale_method": (
                            "1.4826*MAD per 3.0-s MI; P10/median/P90 across 20 MI trials"
                        ),
                        "amplitude_scale_domain": (
                            "bundle stream-preprocessed signal; filter-bank: median MAD across bands"
                        ),
                        "amplitude_channel_names": ",".join(runtime.selected_channels),
                        "training_channel_scale": _csv_vector(
                            amplitude_result["training_scale"]
                        ),
                        "today_channel_lower": _csv_vector(
                            amplitude_result["today_lower"]
                        ),
                        "today_channel_median": _csv_vector(
                            amplitude_result["today_median"]
                        ),
                        "today_channel_upper": _csv_vector(
                            amplitude_result["today_upper"]
                        ),
                        "initial_raw_channel_gain": _csv_vector(
                            amplitude_result["raw_gain"]
                        ),
                        "initial_applied_channel_gain": _csv_vector(
                            amplitude_result["applied_gain"]
                        ),
                        "amplitude_range_low_percentile": f"{AMPLITUDE_RANGE_LOW_PERCENTILE:.1f}",
                        "amplitude_range_high_percentile": f"{AMPLITUDE_RANGE_HIGH_PERCENTILE:.1f}",
                        "amplitude_current_window_s": f"{AMPLITUDE_CURRENT_WINDOW:.3f}",
                        "amplitude_out_of_range_streak": AMPLITUDE_OUT_OF_RANGE_STREAK,
                        "amplitude_gain_smoothing_alpha": f"{AMPLITUDE_GAIN_SMOOTHING_ALPHA:.4f}",
                        "amplitude_gain_min": f"{AMPLITUDE_GAIN_MIN:.4f}",
                        "amplitude_gain_max": f"{AMPLITUDE_GAIN_MAX:.4f}",
                        "original_threshold": f"{original_threshold:.8f}",
                        "calibration_threshold": f"{calibration_threshold:.8f}",
                        "original_weight": f"{ORIGINAL_THRESHOLD_WEIGHT:.2f}",
                        "calibration_weight": f"{CALIBRATION_THRESHOLD_WEIGHT:.2f}",
                        "applied_threshold": f"{applied_threshold:.8f}",
                        "best_calibration_balanced_accuracy": (
                            f"{calibration_balanced_accuracy:.8f}"
                        ),
                        "accuracy_at_original_threshold": (
                            f"{original_calibration_accuracy:.8f}"
                        ),
                        "accuracy_at_applied_threshold": (
                            f"{applied_calibration_accuracy:.8f}"
                        ),
                        "finetuning_applied": int(finetuning_result["applied"]),
                        "finetuning_reason": finetuning_result["reason"],
                        "baseline_auc": (
                            ""
                            if finetuning_result["baseline"] is None
                            else f"{finetuning_result['baseline']['auc']:.8f}"
                        ),
                        "finetuned_oof_auc": (
                            ""
                            if finetuning_result["candidate"] is None
                            else f"{finetuning_result['candidate']['auc']:.8f}"
                        ),
                        "finetuned_oof_balanced_accuracy": (
                            ""
                            if finetuning_result["candidate"] is None
                            else f"{finetuning_result['candidate']['balanced_accuracy']:.8f}"
                        ),
                        "finetuned_oof_left_recall": (
                            ""
                            if finetuning_result["candidate"] is None
                            else f"{finetuning_result['candidate']['left_recall']:.8f}"
                        ),
                        "finetuned_oof_right_recall": (
                            ""
                            if finetuning_result["candidate"] is None
                            else f"{finetuning_result['candidate']['right_recall']:.8f}"
                        ),
                    }
                )

            print("-" * 78)
            print(
                "Initial channel gain  : "
                + ", ".join(
                    f"{ch}={gain:.4f}"
                    for ch, gain in zip(
                        runtime.selected_channels, amplitude_result["applied_gain"]
                    )
                )
            )
            print(f"Original threshold    : {original_threshold:.6f}")
            print(
                f"Fine-tuning applied   : {finetuning_result['applied']} "
                f"({finetuning_result['reason']})"
            )
            if finetuning_result["baseline"] is not None:
                print(
                    f"Baseline AUC          : "
                    f"{finetuning_result['baseline']['auc']:.4f}"
                )
            if finetuning_result["candidate"] is not None:
                candidate_metrics = finetuning_result["candidate"]
                print(
                    "Fine-tuned OOF        : "
                    f"AUC={candidate_metrics['auc']:.4f}, "
                    f"BA={candidate_metrics['balanced_accuracy']:.4f}, "
                    f"L-recall={candidate_metrics['left_recall']:.4f}, "
                    f"R-recall={candidate_metrics['right_recall']:.4f}"
                )
            print(f"Calibration threshold : {calibration_threshold:.6f}")
            if finetuning_result["applied"]:
                print(
                    f"Applied threshold     : {applied_threshold:.6f} "
                    f"(Fixed to 0.50 for newly fine-tuned model)"
                )
            else:
                print(
                    f"Applied threshold     : {applied_threshold:.6f} "
                    f"({ORIGINAL_THRESHOLD_WEIGHT:.0%} old + "
                    f"{CALIBRATION_THRESHOLD_WEIGHT:.0%} calibration)"
                )
            print(
                f"Calibration BA        : {calibration_balanced_accuracy * 100.0:.2f}%"
            )
            print("=" * 78 + "\n")

            ui.show_calibration_summary(
                original_threshold,
                calibration_threshold,
                applied_threshold,
                calibration_balanced_accuracy,
                finetuning_result["applied"],
            )

            # 5-s RELAX immediately before the 30-trial main experiment.
            ui.show_main_relax(MAIN_RELAX_DURATION, explore)
            explore.set_marker(MAIN_EXPERIMENT_START)

            # =================================================================
            # Main experiment: validated daily head (or original fallback)
            # + session-calibrated threshold
            # =================================================================
            for trial_number in range(1, N_TRIALS + 1):
                target_direction = target_schedule[trial_number - 1]

                # Reset gain at the start of every trial so a temporary realtime
                # correction from the previous trial never carries over.
                # amplitude_result["applied_gain"] is the calibration initial_gain.
                runtime.set_channel_gain(amplitude_result["applied_gain"])

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

                amplitude_current_scale_sequence = []
                amplitude_outside_range_sequence = []
                amplitude_update_eligible_sequence = []
                amplitude_raw_target_gain_sequence = []
                amplitude_applied_gain_sequence = []
                amplitude_out_of_range_streak = np.zeros(
                    len(runtime.selected_channels), dtype=int
                )

                actual_wall_time = None
                decision_time = None

                # 3) Exact, non-overlapping 0.5-s windows: 0-0.5, 0.5-1.0, ...
                for prediction_index in range(1, MAX_PREDICTIONS + 1):
                    window_start = (
                        classification_start_sample
                        + (prediction_index - 1) * window_samples
                    )

                    # Realtime amplitude adaptation starts only after a full 1.0 s
                    # of MI has accumulated.  The preceding 1.0-s segment is read
                    # from the pre-gain stream, compared with today's robust range,
                    # and can update the gain used for the NEXT 0.5-s model window.
                    if (
                        ENABLE_AMPLITUDE_NORMALIZATION
                        and window_start - classification_start_sample >= amplitude_window_samples
                    ):
                        amplitude_segment = runtime.get_processed_segment(
                            window_start - amplitude_window_samples,
                            amplitude_window_samples,
                            timeout=2.0,
                        )
                        amp_update = update_realtime_amplitude_gain(
                            runtime=runtime,
                            current_segment=amplitude_segment,
                            amplitude_profile=amplitude_result,
                            out_of_range_streak=amplitude_out_of_range_streak,
                        )
                        amplitude_out_of_range_streak = amp_update[
                            "out_of_range_streak"
                        ]
                        amplitude_current_scale_sequence.append(
                            _csv_vector(amp_update["current_scale"])
                        )
                        amplitude_outside_range_sequence.append(
                            _csv_vector(amp_update["outside"].astype(int))
                        )
                        amplitude_update_eligible_sequence.append(
                            _csv_vector(amp_update["eligible"].astype(int))
                        )
                        amplitude_raw_target_gain_sequence.append(
                            _csv_vector(amp_update["raw_target_gain"])
                        )
                    else:
                        amplitude_current_scale_sequence.append("")
                        amplitude_outside_range_sequence.append("")
                        amplitude_update_eligible_sequence.append("")
                        amplitude_raw_target_gain_sequence.append("")

                    amplitude_applied_gain_sequence.append(
                        _csv_vector(runtime.channel_gain)
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
                    "original_threshold": f"{original_threshold:.8f}",
                    "calibration_threshold": f"{calibration_threshold:.8f}",
                    "applied_threshold": f"{applied_threshold:.8f}",
                    "finetuning_applied": int(finetuning_result["applied"]),
                    "finetuning_reason": finetuning_result["reason"],
                    "amplitude_normalization_enabled": int(ENABLE_AMPLITUDE_NORMALIZATION),
                    "applied_channel_gain": _csv_vector(runtime.channel_gain),
                    "amplitude_current_scale_sequence": ";".join(
                        amplitude_current_scale_sequence
                    ),
                    "amplitude_outside_range_sequence": ";".join(
                        amplitude_outside_range_sequence
                    ),
                    "amplitude_update_eligible_sequence": ";".join(
                        amplitude_update_eligible_sequence
                    ),
                    "amplitude_raw_target_gain_sequence": ";".join(
                        amplitude_raw_target_gain_sequence
                    ),
                    "amplitude_applied_gain_sequence": ";".join(
                        amplitude_applied_gain_sequence
                    ),
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
                    f"gain={_csv_vector(runtime.channel_gain)} | "
                    f"pred={''.join(prediction_sequence)}"
                )
                
                # 10, 20 Trial 종료 시 5초 휴식 (마지막 30 Trial 제외)
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
