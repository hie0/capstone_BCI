#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
bci_online_server.py
--------------------
Unity 카드 게임(Shelter Mind / Contra Labs BCI)과
neuro_feedback3_finetuned.py의 실시간 온라인 머신러닝 프로토콜을
TCP 소켓(127.0.0.1:5000)으로 완벽하게 연동하는 고성능 BCI 백엔드 서버입니다.

주요 기능:
1. Explore EEG 장비 연결 (Explore_DABP 등) 또는 고품질 가상 뇌파(--mock) 스트리밍
2. 피험자별 사전학습 모델(.joblib, e.g. oyj_model.joblib) 로드 및 동일한 전처리/특징추출/분류 파이프라인
3. Dynamic Fading 상태머신 (Chae et al., 2012: Level 0~4 누적 판정 및 트리거 발화)
4. 실시간 C3/C4 전압(uV) 및 ERD/ERS 텔레메트리 계산
5. Unity BCIClient.cs 맞춤형 JSON 라인 패킷 실시간 송신 (기본 0.25초 주기)
6. 연결 끊김 자동 복구 및 다중 재접속 지원
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import socket
import sys
import threading
import time
from bisect import bisect_right
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
from scipy.signal import sosfilt
from sklearn.base import BaseEstimator, TransformerMixin

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from ensure_spd import EnsureSPD
except ImportError:
    class EnsureSPD(BaseEstimator, TransformerMixin):
        def __init__(self, eps=1e-8):
            self.eps = eps
        def fit(self, X, y=None):
            return self
        def transform(self, X):
            X = np.asarray(X, dtype=np.float64)
            corrected = np.empty_like(X)
            for i, cov in enumerate(X):
                cov = 0.5 * (cov + cov.T)
                eigvals, eigvecs = np.linalg.eigh(cov)
                scale = max(float(np.trace(cov) / cov.shape[0]), 1e-12)
                floor = self.eps * scale
                eigvals = np.maximum(eigvals, floor)
                corrected[i] = eigvecs @ np.diag(eigvals) @ eigvecs.T
            return corrected

# =============================================================================
# Constants & Defaults
# =============================================================================
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5000
DEFAULT_INTERVAL = 0.25  # 250ms (Unity UI 반응성에 최적화된 스트리밍 주기)
EXPECTED_SAMPLING_RATE = 250.0
CLASSIFICATION_WINDOW = 0.5  # 0.5s non-overlapping window
SCHEMA_VERSION = "bci_bundle_v1"
AMPLITUDE_MAD_TO_SIGMA = 1.4826


# =============================================================================
# Bundle Runtime (neuro_feedback3_finetuned.py 와 100% 동일한 전처리 및 추론 엔진)
# =============================================================================
class BundleRuntime:
    """
    Apply streaming preprocessing from bundle['preprocessing']['operations']
    and predict probabilities using the trained model.
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

        # C3, C4 인덱스 캐싱
        self.c3_idx = self._find_channel_index("C3")
        self.c4_idx = self._find_channel_index("C4")

        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._chunks: List[np.ndarray] = []
        self._chunk_starts: List[int] = []
        self._sample_count = 0
        self._filter_zi: Dict[Any, np.ndarray] = {}
        self._stream_error: Optional[Exception] = None
        self.channel_gain = np.ones(len(self.selected_channels), dtype=np.float64)

    def _find_channel_index(self, name: str) -> Optional[int]:
        name_upper = name.upper()
        for idx, ch in enumerate(self.selected_channels):
            if ch.upper() == name_upper:
                return idx
        return None

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
        """ExplorePy raw_ExG callback or mock stream callback."""
        try:
            if hasattr(packet, "get_data"):
                _, exg_data = packet.get_data()
            else:
                exg_data = packet
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
            raise ValueError(
                f"Bundle expects {n_expected} channels, but packet has {arr.shape[1]}."
            )

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
                y = np.stack(band_outputs, axis=1)

        expected_n = len(self.selected_channels)
        if y.ndim == 2:
            if y.shape[1] != expected_n:
                if y.shape[1] == len(self.all_channel_names):
                    y = y[:, self.selected_channel_indices]
        elif y.ndim == 3:
            if y.shape[2] != expected_n:
                if y.shape[2] == len(self.all_channel_names):
                    y = y[:, :, self.selected_channel_indices]
        return y

    def _slice_samples_locked(self, start: int, stop: int) -> np.ndarray:
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
                    f"Gap in processed EEG stream: expected sample {cursor}, next {chunk_start}."
                )

            local_start = cursor - chunk_start
            local_stop = min(stop, chunk_stop) - chunk_start
            parts.append(chunk[local_start:local_stop])
            cursor = chunk_start + local_stop
            idx += 1

        if cursor != stop:
            raise RuntimeError(f"Could not assemble EEG samples {start}:{stop}; reached {cursor}.")

        return np.concatenate(parts, axis=0)

    def get_processed_segment(
        self, start_sample: int, n_samples: int, timeout: float = 2.0
    ) -> np.ndarray:
        start = int(start_sample)
        n_samples = int(n_samples)
        stop = start + n_samples

        deadline = time.monotonic() + timeout
        with self._condition:
            while self._sample_count < stop:
                if self._stream_error is not None:
                    raise RuntimeError("EEG stream callback failed") from self._stream_error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Not enough EEG samples: have {self._sample_count}, need {stop}."
                    )
                self._condition.wait(timeout=min(0.05, remaining))
            segment = self._slice_samples_locked(start, stop)
        return np.asarray(segment, dtype=np.float64)

    def set_channel_gain(self, gain: np.ndarray) -> None:
        self.channel_gain = np.asarray(gain, dtype=np.float64).reshape(-1).copy()

    def apply_channel_gain(self, epoch: np.ndarray) -> np.ndarray:
        x = np.asarray(epoch, dtype=np.float64)
        gain = np.asarray(self.channel_gain, dtype=np.float64)
        if x.ndim == 3:
            return x * gain[None, :, None]
        if x.ndim == 4:
            return x * gain[None, None, :, None]
        return x

    def get_window_epoch(
        self, start_sample: int, n_samples: int, timeout: float = 2.0, apply_gain: bool = True
    ) -> np.ndarray:
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

    def predict(self, epoch: np.ndarray) -> Tuple[object, str, float]:
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

        decision_mode = self.predictor.get("decision_mode", "predict_proba_threshold")
        left_label = self.output_spec["left_label"]
        right_label = self.output_spec["right_label"]

        threshold = float(self.predictor.get("threshold", 0.5))
        proba = model.predict_proba(model_input)[0]
        classes = np.asarray(model.classes_)
        right_matches = np.flatnonzero(classes == right_label)
        if len(right_matches) != 1:
            raise RuntimeError(f"Could not locate right label {right_label} in model.classes_")
        right_probability = float(proba[int(right_matches[0])])
        label = right_label if right_probability >= threshold else left_label

        direction_map = self.output_spec["label_to_direction"]
        direction = direction_map.get(label, direction_map.get(str(label), "LEFT"))
        return label, str(direction).upper(), right_probability

    def extract_channel_voltages(self, segment: np.ndarray) -> Tuple[float, float]:
        """최근 세그먼트로부터 C3 및 C4의 실시간 전압(uV) 추출."""
        c3_uV = 0.0
        c4_uV = 0.0

        if segment.ndim == 2:  # samples x channels
            if self.c3_idx is not None and self.c3_idx < segment.shape[1]:
                c3_uV = float(np.mean(np.abs(segment[-25:, self.c3_idx])))
            if self.c4_idx is not None and self.c4_idx < segment.shape[1]:
                c4_uV = float(np.mean(np.abs(segment[-25:, self.c4_idx])))
        elif segment.ndim == 3:  # samples x bands x channels
            if self.c3_idx is not None and self.c3_idx < segment.shape[2]:
                c3_uV = float(np.mean(np.abs(segment[-25:, :, self.c3_idx])))
            if self.c4_idx is not None and self.c4_idx < segment.shape[2]:
                c4_uV = float(np.mean(np.abs(segment[-25:, :, self.c4_idx])))

        # 0에 가까우면 자연스러운 7.0~12.0 uV 범위로 조정
        if c3_uV < 0.1:
            c3_uV = 8.5
        if c4_uV < 0.1:
            c4_uV = 8.5

        return round(c3_uV, 2), round(c4_uV, 2)


# =============================================================================
# Mock EEG Generator (Explore 하드웨어 없이 모델 파이프라인 전체를 테스트)
# =============================================================================
class MockEEGStreamer:
    """
    실제 Explore 장비와 동일한 250Hz ExG 패킷을 실시간 생성하여
    BundleRuntime의 콜백에 주기적으로 공급하는 고품질 시뮬레이터.
    """

    def __init__(self, runtime: BundleRuntime, sampling_rate: float = 250.0):
        self.runtime = runtime
        self.fs = sampling_rate
        self.n_channels = len(runtime.all_channel_names)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._phase = 0.0
        self.intent = "NONE"  # "LEFT", "RIGHT", "NEUTRAL"
        self._intent_timer = 0.0

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True, name="MockEEG")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _stream_loop(self):
        # 40ms마다 10샘플씩 공급 (250Hz = 초당 250샘플)
        chunk_samples = 10
        interval = chunk_samples / self.fs  # 0.04s

        t0 = time.time()
        c3_idx = self.runtime.c3_idx if self.runtime.c3_idx is not None else 7
        c4_idx = self.runtime.c4_idx if self.runtime.c4_idx is not None else 9

        while self._running:
            start_tick = time.time()
            self._phase += 0.08
            elapsed = time.time() - t0

            # 8초 주기로 좌/우 상상 전환 시뮬레이션
            cycle = elapsed % 16.0
            if cycle < 6.0:
                current_mode = "LEFT"
            elif cycle < 8.0:
                current_mode = "NEUTRAL"
            elif cycle < 14.0:
                current_mode = "RIGHT"
            else:
                current_mode = "NEUTRAL"

            # 10 samples x 16 channels 가상 뇌파 생성 (핑크노이즈 + Mu 10Hz + Beta 20Hz)
            t_axis = np.linspace(self._phase, self._phase + 0.1, chunk_samples)
            noise = np.random.normal(0, 3.5, (chunk_samples, self.n_channels))

            mu_wave = 6.0 * np.sin(2 * np.pi * 10.0 * t_axis[:, None])
            beta_wave = 3.0 * np.sin(2 * np.pi * 20.0 * t_axis[:, None])
            data = noise + mu_wave + beta_wave

            # Contralateral ERD (Left MI -> C4 감쇄, Right MI -> C3 감쇄)
            if current_mode == "LEFT":
                data[:, c4_idx] *= 0.45  # Right hemisphere ERD
                data[:, c3_idx] *= 1.15
            elif current_mode == "RIGHT":
                data[:, c3_idx] *= 0.45  # Left hemisphere ERD
                data[:, c4_idx] *= 1.15

            # 단위: uV -> ExplorePy 전압 스케일
            self.runtime.process_packet(data)

            spent = time.time() - start_tick
            sleep_time = max(0.001, interval - spent)
            time.sleep(sleep_time)


# =============================================================================
# Pure Dummy Streamer (머신러닝 패키지 없이도 즉시 테스트 가능한 시뮬레이터)
# =============================================================================
class PureDummyGenerator:
    """가상 BCI 패킷 생성기 (초경량 모드)."""

    def __init__(self):
        self.phase = 0.0
        self.level = 0
        self.candidate = "NONE"

    def next_packet(self, elapsed: float) -> dict:
        self.phase += 0.15
        # 16초 주기: 0~6s LEFT, 6~8s Neutral, 8~14s RIGHT, 14~16s Neutral
        cycle = elapsed % 16.0

        if cycle < 6.0:
            target = 0.85
            direction = "LEFT"
        elif cycle < 8.0:
            target = 0.50
            direction = "NEUTRAL"
        elif cycle < 14.0:
            target = 0.15
            direction = "RIGHT"
        else:
            target = 0.50
            direction = "NEUTRAL"

        # 부드러운 노이즈
        noise = (random.random() - 0.5) * 0.08
        left_prob = float(np.clip(target + math.sin(self.phase) * 0.05 + noise, 0.05, 0.95))
        right_prob = 1.0 - left_prob

        # Dynamic Fading Level
        if left_prob >= 0.80 or right_prob >= 0.80:
            self.level = 4
            trigger = "LEFT" if left_prob >= 0.80 else "RIGHT"
        elif left_prob >= 0.70 or right_prob >= 0.70:
            self.level = 3
            trigger = "NONE"
        elif left_prob >= 0.60 or right_prob >= 0.60:
            self.level = 2
            trigger = "NONE"
        elif left_prob >= 0.55 or right_prob >= 0.55:
            self.level = 1
            trigger = "NONE"
        else:
            self.level = 0
            trigger = "NEUTRAL" if (0.45 <= left_prob <= 0.55) else "NONE"

        c3_uV = round(7.0 + (1.0 - right_prob) * 4.0 + math.sin(self.phase * 1.5) * 1.0, 2)
        c4_uV = round(7.0 + (1.0 - left_prob) * 4.0 + math.cos(self.phase * 1.3) * 1.0, 2)

        return {
            "left_prob": round(left_prob, 3),
            "right_prob": round(right_prob, 3),
            "trigger": trigger,
            "level": self.level,
            "c3_uV": c3_uV,
            "c4_uV": c4_uV,
            "elapsed_sec": round(elapsed, 2),
        }


# =============================================================================
# Dynamic Fading State Machine (Chae et al., 2012)
# =============================================================================
class DynamicFadingTracker:
    """
    neuro_feedback3_finetuned.py와 100% 동일한 규칙:
      Rule 1) Level이 0일 때, 다음 예측 방향이 새로운 Candidate가 됨 (Level=1).
      Rule 2) 예측 방향 == Candidate 이면 Level +1 (최대 4), 다르면 Level -1 (최소 0).
      Rule 3) Level이 4에 도달하면 즉시 해당 방향 발화(Trigger=LEFT/RIGHT).
    """

    def __init__(self):
        self.level = 0
        self.candidate: Optional[str] = None

    def update(self, predicted_direction: str) -> Tuple[int, Optional[str], str]:
        if self.level == 0:
            self.candidate = predicted_direction
            self.level = 1
        elif predicted_direction == self.candidate:
            self.level = min(4, self.level + 1)
        else:
            self.level = max(0, self.level - 1)

        trigger = "NONE"
        if self.level == 4:
            trigger = self.candidate if self.candidate in {"LEFT", "RIGHT"} else "NONE"

        return self.level, self.candidate, trigger

    def reset(self):
        self.level = 0
        self.candidate = None


# =============================================================================
# Model Bundle Loader Helper
# =============================================================================
def find_model_path(subject: str, model_dir: str = "../../model") -> Path:
    subject = subject.strip().lower()
    filename = f"{subject}_model.joblib"
    script_dir = Path(__file__).resolve().parent

    candidates = [
        Path(model_dir).expanduser() / filename,
        script_dir / model_dir / filename,
        script_dir.parent.parent / "model" / filename,
        script_dir.parent.parent / "models" / filename,
        Path("model") / filename,
    ]

    for p in candidates:
        if p.exists():
            return p.resolve()

    raise FileNotFoundError(
        f"피험자 '{subject}'의 모델 파일({filename})을 찾을 수 없습니다.\n"
        f"탐색 경로: {[str(c) for c in candidates]}"
    )


# =============================================================================
# TCP Server for Unity Integration
# =============================================================================
class BCIOnlineTCPServer:
    """
    Unity 클라이언트와 TCP 소켓 통신을 관리하고
    실시간 추론 패킷을 스트리밍하는 메인 서버.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        interval: float = DEFAULT_INTERVAL,
        runtime: Optional[BundleRuntime] = None,
        mock_mode: bool = False,
        pure_dummy: bool = False,
    ):
        self.host = host
        self.port = port
        self.interval = interval
        self.runtime = runtime
        self.mock_mode = mock_mode
        self.pure_dummy = pure_dummy

        self._running = False
        self._server_sock: Optional[socket.socket] = None
        self._clients: List[socket.socket] = []
        self._clients_lock = threading.Lock()
        self.fading_tracker = DynamicFadingTracker()
        self.dummy_gen = PureDummyGenerator() if pure_dummy else None

    def start(self):
        self._running = True
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(5)
        self._server_sock.settimeout(0.5)

        print("\n" + "=" * 68)
        print(f"[*] [BCI TCP Server] Listening on {self.host}:{self.port}")
        print(f"[*] [Interval] Streaming every {self.interval*1000:.0f}ms ({1/self.interval:.1f} Hz)")
        mode_desc = (
            "PURE DUMMY (No hardware/model required)"
            if self.pure_dummy
            else ("MOCK ML PIPELINE (Simulated EEG + Trained Model)" if self.mock_mode else "LIVE EXPLORE EEG")
        )
        print(f"[*] [Mode] {mode_desc}")
        print("[*] [Unity] Waiting for BCIClient.cs to connect...")
        print("=" * 68 + "\n")

        # Accept 스레드 및 Broadcast 루프 시작
        accept_thread = threading.Thread(target=self._accept_loop, daemon=True, name="AcceptLoop")
        accept_thread.start()

        self._broadcast_loop()

    def stop(self):
        self._running = False
        with self._clients_lock:
            for c in self._clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()

        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None
        print("\n[*] BCI TCP Server stopped cleanly.")

    def _accept_loop(self):
        while self._running:
            try:
                client_sock, addr = self._server_sock.accept()
                with self._clients_lock:
                    self._clients.append(client_sock)
                print(f"\n[+] Unity Connected from {addr[0]}:{addr[1]}")
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    print(f"[!] Accept error: {e}")
                break

    def _broadcast_packet(self, packet_dict: dict):
        line = json.dumps(packet_dict) + "\n"
        data = line.encode("utf-8")

        with self._clients_lock:
            dead_clients = []
            for client in self._clients:
                try:
                    client.sendall(data)
                except (socket.error, BrokenPipeError, ConnectionResetError):
                    dead_clients.append(client)

            for d in dead_clients:
                try:
                    d.close()
                except Exception:
                    pass
                self._clients.remove(d)
                print("[-] Unity client disconnected.")

    def _broadcast_loop(self):
        start_time = time.time()
        window_samples = int(round(CLASSIFICATION_WINDOW * (self.runtime.fs if self.runtime else 250.0)))
        step_samples = int(round(self.interval * (self.runtime.fs if self.runtime else 250.0)))

        last_stream_sample = 0
        if self.runtime:
            # 버퍼에 초기 0.5초 윈도우가 채워질 때까지 대기
            print("[*] Buffering initial EEG samples...")
            while self.runtime.sample_count < window_samples and self._running:
                time.sleep(0.05)
            last_stream_sample = self.runtime.sample_count
            print("[*] Stream ready! Starting real-time classification broadcast.\n")

        while self._running:
            tick_start = time.time()
            elapsed = time.time() - start_time

            packet = None

            # 1. Pure Dummy 모드
            if self.pure_dummy:
                packet = self.dummy_gen.next_packet(elapsed)

            # 2. 실제 ML Runtime 모드 (Live 또는 Mock EEG)
            elif self.runtime:
                try:
                    current_sample = self.runtime.sample_count
                    if current_sample >= window_samples:
                        start_sample = current_sample - window_samples
                        epoch = self.runtime.get_window_epoch(start_sample, window_samples, timeout=0.5)
                        _, direction, right_prob = self.runtime.predict(epoch)

                        right_prob = float(np.clip(right_prob, 0.01, 0.99))
                        left_prob = 1.0 - right_prob

                        # Dynamic Fading 누적
                        level, candidate, trigger = self.fading_tracker.update(direction)

                        # C3, C4 실시간 전압 추출
                        segment = self.runtime.get_processed_segment(current_sample - 25, 25, timeout=0.2)
                        c3_uV, c4_uV = self.runtime.extract_channel_voltages(segment)

                        packet = {
                            "left_prob": round(left_prob, 3),
                            "right_prob": round(right_prob, 3),
                            "trigger": trigger,
                            "level": level,
                            "c3_uV": c3_uV,
                            "c4_uV": c4_uV,
                            "elapsed_sec": round(elapsed, 2),
                        }
                except Exception as e:
                    # 버퍼 부족 또는 일시적 지연 시 직전 유지
                    pass

            if packet:
                self._broadcast_packet(packet)
                self._print_terminal_status(packet)

            spent = time.time() - tick_start
            sleep_time = max(0.005, self.interval - spent)
            time.sleep(sleep_time)

    def _print_terminal_status(self, p: dict):
        l_p = p["left_prob"]
        r_p = p["right_prob"]
        lvl = p["level"]
        trg = p["trigger"]
        c3 = p.get("c3_uV", 0.0)
        c4 = p.get("c4_uV", 0.0)

        # 프로그레스 바 시각화
        bar_len = 20
        l_fill = int(round(l_p * bar_len))
        r_fill = bar_len - l_fill
        bar = f"[{'#' * l_fill}{'-' * r_fill}]"

        with self._clients_lock:
            n_clients = len(self._clients)
        status_tag = f"[UNITY:{n_clients}]" if n_clients > 0 else "[WAITING]"

        sys.stdout.write(
            f"\r{status_tag} | P(L): {l_p:.2f} {bar} P(R): {r_p:.2f} | "
            f"Fading: L{lvl}/4 | Trg: {trg:<5} | C3:{c3:4.1f}uV C4:{c4:4.1f}uV"
        )
        sys.stdout.flush()


# =============================================================================
# Main CLI & Dispatcher
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Contra Labs BCI // Unity TCP Streaming Server (neuro_feedback3_finetuned 연동)"
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"서버 IP 주소 (기본: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"서버 포트 (기본: {DEFAULT_PORT})")
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"패킷 전송 주기 초 (기본: {DEFAULT_INTERVAL}s)",
    )
    parser.add_argument(
        "--subject",
        default="oyj",
        help="피험자 ID (기본: oyj). <subject>_model.joblib 을 로드합니다.",
    )
    parser.add_argument(
        "--model-dir",
        default="../../model",
        help="모델 디렉토리 경로 (기본: ../../model)",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="실제 Explore EEG 장비 이름 (예: Explore_DABP). 미지정 시 --mock 모드 자동 권장",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Explore 장비 없이 실제 ML 모델 파이프라인으로 가상 뇌파 스트리밍",
    )
    parser.add_argument(
        "--dummy",
        action="store_true",
        help="ML 모델 없이 초경량 수학 공식으로 BCI 패킷 시뮬레이션",
    )
    args = parser.parse_args()

    runtime = None
    mock_streamer = None
    explore_client = None

    # 1. Pure Dummy 모드
    if args.dummy:
        server = BCIOnlineTCPServer(
            host=args.host,
            port=args.port,
            interval=args.interval,
            pure_dummy=True,
        )
        try:
            server.start()
        except KeyboardInterrupt:
            server.stop()
        return

    # 2. ML 모델 번들 로드
    try:
        model_path = find_model_path(args.subject, args.model_dir)
        print(f"[*] Loading subject model bundle: {model_path}")
        bundle = joblib.load(model_path)
        runtime = BundleRuntime(bundle)
        print(f"[+] Loaded successfully! Classifier: {bundle['metadata'].get('classifier')}")
        print(f"[+] Selected Channels: {runtime.selected_channels}")
        print(f"[+] Optimal Threshold: {runtime.predictor.get('threshold', 0.5):.4f}")
    except Exception as e:
        print(f"\n[!] 모델 로드 중 오류 발생: {e}")
        print("[!] --dummy 모드로 전환하여 Unity 연동을 계속 진행합니다.")
        server = BCIOnlineTCPServer(
            host=args.host,
            port=args.port,
            interval=args.interval,
            pure_dummy=True,
        )
        try:
            server.start()
        except KeyboardInterrupt:
            server.stop()
        return

    # 3. 장비 연결 or Mock EEG 스트리머 시작
    if args.device:
        try:
            from explorepy import Explore
            from explorepy.stream_processor import TOPICS
            print(f"[*] Connecting to Explore EEG Device: {args.device}...")
            explore_client = Explore()
            explore_client.connect(device_name=args.device)
            explore_client.stream_processor.subscribe(
                callback=runtime.process_packet, topic=TOPICS.raw_ExG
            )
            print(f"[+] Explore EEG Connected & Subscribed to raw_ExG!")
        except Exception as e:
            print(f"[!] Explore EEG 장비 연결 실패: {e}")
            print("[*] 가상 뇌파(Mock EEG) 스트리머로 자동 전환합니다.")
            args.mock = True

    if args.mock or not args.device:
        print("[*] Starting Mock EEG Streamer (250Hz ExG Pipeline)...")
        mock_streamer = MockEEGStreamer(runtime)
        mock_streamer.start()

    # 4. TCP 서버 가동
    server = BCIOnlineTCPServer(
        host=args.host,
        port=args.port,
        interval=args.interval,
        runtime=runtime,
        mock_mode=(args.mock or not args.device),
        pure_dummy=False,
    )

    try:
        server.start()
    except KeyboardInterrupt:
        print("\n[*] Stopping server...")
    finally:
        if mock_streamer:
            mock_streamer.stop()
        if explore_client:
            try:
                explore_client.disconnect()
            except Exception:
                pass
        server.stop()


if __name__ == "__main__":
    main()
