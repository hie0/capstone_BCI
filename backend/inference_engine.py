# -*- coding: utf-8 -*-
"""
Real-Time & Chronological EEG Inference Manager (`backend/inference_engine.py`)
===============================================================================
Loads the exported `.joblib` fitted models and local EEG session data, manages
stateful chronological TTA sessions (`CausalEA` + `CausalLogitCenter` + `ArtGate90`),
and computes all predictions and session/cohort metrics dynamically from real model inference.
"""
from __future__ import annotations

import os
import pickle
import re
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.signal import sosfilt
from scipy.stats import ttest_rel, wilcoxon
from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score

from backend.research_protocol import (
    ELECTRODE_NAMES_16,
    FS,
    IDX_EOG,
    ONLINE_BAND_SOS,
    PARTICIPANT_SPECS,
    POSTER_GOLDEN_DATES,
    SOS_NOTCH,
    Calib20FittedModel,
    OfflineSubjectFittedModel,
    StatefulOfflineSubjectSession,
    StatefulOnlineTTASession,
    resolve_data_root,
)

BACKEND_DIR = Path(__file__).resolve().parent
MODELS_DIR = BACKEND_DIR / "models"
LOCAL_CACHE_DIR = BACKEND_DIR / "local_cache"
DATA_ROOT = resolve_data_root()


class NeurolinkInferenceManager:
    """
    Central manager for exported `.joblib` models, local EEG trial streams,
    and stateful chronological TTA inference sessions.
    """

    def __init__(self) -> None:
        self.online_models_map: dict[str, dict[str, Any]] = {}
        self.offline_models_map: dict[str, dict[str, OfflineSubjectFittedModel]] = {}
        self.raw_sessions_map: dict[str, dict[str, Any]] = {}
        self.sessions_by_subject: dict[str, list[dict[str, Any]]] = {
            "WMJ": [], "KGE": [], "OYJ": [], "KHY": []
        }
        self.golden_sessions_by_subject: dict[str, list[dict[str, Any]]] = {
            "WMJ": [], "KGE": [], "OYJ": [], "KHY": []
        }
        # Stateful active sessions keyed by session_state_key
        self.active_online_states: dict[str, StatefulOnlineTTASession] = {}
        self.active_offline_states: dict[str, StatefulOfflineSubjectSession] = {}
        self.loaded: bool = False

    def load_all(self) -> None:
        if self.loaded:
            return

        # 1. Load exported online session Calib20 models (.joblib)
        online_joblib = MODELS_DIR / "online_50sessions_calib_models.joblib"
        if online_joblib.exists():
            self.online_models_map = joblib.load(online_joblib)

        # 2. Load exported per-subject offline champion models (.joblib)
        for subj in ("WMJ", "KGE", "OYJ", "KHY"):
            p = MODELS_DIR / f"{subj.lower()}_final_model.joblib"
            if p.exists():
                self.offline_models_map[subj] = joblib.load(p)

        # 3. Load local gitignored EEG cache (or dynamically extract from DATA_ROOT if needed)
        cache_pkl = LOCAL_CACHE_DIR / "calibrated_81_sessions.pkl"
        if cache_pkl.exists():
            with open(cache_pkl, "rb") as f:
                sessions_list = pickle.load(f)
            for s in sessions_list:
                key = f"{s['subject']}__{s['session']}"
                self.raw_sessions_map[key] = s

        # Index sessions by subject (Golden 50 first, sorted by date & session name)
        for subj in ("WMJ", "KGE", "OYJ", "KHY"):
            subj_entries = [
                entry for entry in self.online_models_map.values()
                if entry["subject"] == subj
            ]
            # Sort so golden 16ch sessions come first, ordered by date and session
            subj_entries.sort(
                key=lambda e: (
                    0 if e.get("is_golden_50", False) else (2 if e.get("is_7ch", False) else 1),
                    str(e.get("date", "")),
                    str(e.get("session", "")),
                )
            )
            self.sessions_by_subject[subj] = subj_entries
            self.golden_sessions_by_subject[subj] = [
                e for e in subj_entries if e.get("is_golden_50", False)
            ]

        self.loaded = True

    def resolve_session_entry(self, participant_id: str, session_id: str) -> dict[str, Any]:
        """
        Resolves either an exact session folder name (e.g. 'wmj_online_0930_1')
        or a website alias ('session-01', 'session-02', 'golden-01', '1', etc.)
        to the corresponding session entry for `participant_id`.
        """
        self.load_all()
        subj = participant_id.upper()
        if subj not in self.sessions_by_subject or not self.sessions_by_subject[subj]:
            raise KeyError(f"No calibrated sessions found for participant {subj}")

        # 1. Exact match
        direct_key = f"{subj}__{session_id}"
        if direct_key in self.online_models_map:
            return self.online_models_map[direct_key]

        # 2. Case-insensitive or substring match on session name
        sid_clean = session_id.strip().lower()
        for entry in self.sessions_by_subject[subj]:
            if entry["session"].lower() == sid_clean:
                return entry

        # 3. Alias like "session-01", "session-02", "golden-01", "01"
        m = re.search(r"(\d+)$", sid_clean)
        if m and ("session" in sid_clean or "golden" in sid_clean or sid_clean.isdigit()):
            idx_1based = max(1, int(m.group(1)))
            pool = self.golden_sessions_by_subject[subj] or self.sessions_by_subject[subj]
            chosen = pool[(idx_1based - 1) % len(pool)]
            return chosen

        # Fallback to first golden session
        return (self.golden_sessions_by_subject[subj] or self.sessions_by_subject[subj])[0]

    def resolve_calib_model(
        self,
        participant_id: str,
        session_id: str,
        channel_mode: str,
        tta_enabled: bool,
    ) -> tuple[dict[str, Any], Calib20FittedModel]:
        entry = self.resolve_session_entry(participant_id, session_id)
        models_dict: dict[str, Calib20FittedModel] = entry["models"]
        tta_suffix = "tta_on" if tta_enabled else "tta_off"

        cm = channel_mode.strip().lower()
        if cm in ("optimal", "low", "low_ch", "lowch"):
            cm_key = "low"
        elif cm in ("16", "16ch", "full"):
            cm_key = "16ch"
        elif cm in ("7", "7ch"):
            cm_key = "7ch"
        elif cm in ("5", "5ch"):
            cm_key = "5ch"
        else:
            cm_key = "low"

        candidate_keys = [
            f"{cm_key}__{tta_suffix}",
            f"low__{tta_suffix}",
            f"7ch__{tta_suffix}",
            f"5ch__{tta_suffix}",
        ]
        for k in candidate_keys:
            if k in models_dict:
                return entry, models_dict[k]

        # Fallback to any available model in entry
        first_model = next(iter(models_dict.values()))
        return entry, first_model

    def get_or_create_online_state(
        self,
        participant_id: str,
        session_id: str,
        channel_mode: str,
        tta_enabled: bool,
        client_key: str = "default",
        reset: bool = False,
    ) -> tuple[dict[str, Any], StatefulOnlineTTASession]:
        entry, fmodel = self.resolve_calib_model(participant_id, session_id, channel_mode, tta_enabled)
        state_key = f"{client_key}::{entry['subject']}::{entry['session']}::{fmodel.channel_mode_key}::{tta_enabled}"
        if reset or state_key not in self.active_online_states:
            self.active_online_states[state_key] = StatefulOnlineTTASession(fmodel, tta_override=tta_enabled)
        return entry, self.active_online_states[state_key]

    def get_or_create_offline_state(
        self,
        participant_id: str,
        channel_mode: str,
        tta_enabled: bool,
        client_key: str = "default",
        reset: bool = False,
    ) -> StatefulOfflineSubjectSession:
        self.load_all()
        subj = participant_id.upper()
        subj_bundle = self.offline_models_map.get(subj, {})
        cm = channel_mode.strip().lower()
        if cm not in subj_bundle:
            cm = "low"
        fmodel = subj_bundle[cm]
        state_key = f"{client_key}::OFFLINE::{subj}::{cm}::{tta_enabled}"
        if reset or state_key not in self.active_offline_states:
            self.active_offline_states[state_key] = StatefulOfflineSubjectSession(fmodel, tta_override=tta_enabled)
        return self.active_offline_states[state_key]

    def extract_waveform_snippet(
        self,
        x_16_500: np.ndarray,
        active_channels: list[str],
        downsample_step: int = 2,
    ) -> dict[str, list[float]]:
        """Extracts real EEG waveform snippet (uV) for active channels."""
        out: dict[str, list[float]] = {}
        for ch_name in active_channels:
            if ch_name in ELECTRODE_NAMES_16:
                ch_i = ELECTRODE_NAMES_16.index(ch_name)
                if ch_i < x_16_500.shape[0]:
                    vals = x_16_500[ch_i, ::downsample_step]
                    out[ch_name] = [round(float(v), 3) for v in vals]
        return out

    def predict_single_trial(
        self,
        participant_id: str,
        session_id: str,
        channel_mode: str,
        tta_enabled: bool,
        protocol: str = "online_calib20",
        trial_index: int | None = None,
        eeg_data: list[list[float]] | np.ndarray | None = None,
        is_band_filtered: bool = False,
        eog_ptp_uv: float | None = None,
        true_direction: str | None = None,
        include_waveform: bool = False,
        reset_session_state: bool = False,
        client_key: str = "rest",
    ) -> dict[str, Any]:
        """
        Performs chronological single-trial inference using either:
        1) Custom raw/band-filtered `eeg_data` passed in the request, or
        2) Recorded chronological trial `trial_index` (or next sequential trial) from the selected session.
        """
        self.load_all()
        subj = participant_id.upper()

        if protocol == "offline_champion":
            off_engine = self.get_or_create_offline_state(
                subj, channel_mode, tta_enabled, client_key=client_key, reset=reset_session_state
            )
            if eeg_data is not None:
                x_arr = np.asarray(eeg_data, dtype=np.float64)
                true_int = (1 if true_direction == "RIGHT" else 0) if true_direction in ("LEFT", "RIGHT") else None
                rec = off_engine.step(
                    x_arr,
                    eog_ptp_uv=eog_ptp_uv,
                    true_label_int=true_int,
                )
                if include_waveform and x_arr.ndim == 2:
                    x_oriented = x_arr.T if (x_arr.shape[0] > x_arr.shape[1] and x_arr.shape[1] == 16) else x_arr
                    rec["waveform"] = self.extract_waveform_snippet(x_oriented, off_engine.model.active_channels)
                return rec

        # Online Calib20 + Multi-Crop + CausalEA + CausalLogitCenter protocol
        entry, engine = self.get_or_create_online_state(
            subj, session_id, channel_mode, tta_enabled, client_key=client_key, reset=reset_session_state
        )
        fmodel = engine.model

        if eeg_data is not None:
            x_arr = np.asarray(eeg_data, dtype=np.float64)
            true_int = (1 if true_direction == "RIGHT" else 0) if true_direction in ("LEFT", "RIGHT") else None
            rec = engine.step(
                x_arr,
                eog_ptp_uv=eog_ptp_uv,
                true_label_int=true_int,
                is_band_filtered=is_band_filtered,
            )
            if include_waveform and x_arr.ndim == 2:
                x_oriented = x_arr.T if (x_arr.shape[0] > x_arr.shape[1] and x_arr.shape[1] == 16) else x_arr
                rec["waveform"] = self.extract_waveform_snippet(x_oriented, fmodel.active_channels)
            return rec

        # Use recorded session EEG from local cache
        raw_key = f"{entry['subject']}__{entry['session']}"
        if raw_key not in self.raw_sessions_map:
            raise FileNotFoundError(
                f"Local EEG data for session '{raw_key}' not found in local_cache. "
                "Supply 'eeg_data' directly in the request or ensure BCI_DATA_ROOT / local_cache is present."
            )

        sdata = self.raw_sessions_map[raw_key]
        on = sdata["on"]
        yo = on["y"]
        eog_arr = on["eog"]
        ts_arr = on["timestamps"]
        xo_band = on["bands"][fmodel.band_name]
        n_total = len(yo)

        # If a specific trial_index is requested and it doesn't match engine.step_idx,
        # fast-forward causally from trial 0..trial_index so CausalEA & CausalLogitCenter
        # state at `trial_index` is 100% causally exact!
        target_idx = trial_index if trial_index is not None else (engine.step_idx % n_total)
        target_idx = max(0, min(int(target_idx), n_total - 1))

        if target_idx < engine.step_idx:
            engine.reset()
        while engine.step_idx < target_idx:
            i_prev = engine.step_idx
            engine.step(
                xo_band[i_prev],
                eog_ptp_uv=float(eog_arr[i_prev]),
                true_label_int=int(yo[i_prev]),
                trial_id=i_prev + 1,
                timestamp_s=float(ts_arr[i_prev]),
                is_band_filtered=True,
            )

        rec = engine.step(
            xo_band[target_idx],
            eog_ptp_uv=float(eog_arr[target_idx]),
            true_label_int=int(yo[target_idx]),
            trial_id=target_idx + 1,
            timestamp_s=float(ts_arr[target_idx]),
            is_band_filtered=True,
        )
        if include_waveform:
            rec["waveform"] = self.extract_waveform_snippet(xo_band[target_idx], fmodel.active_channels)
        return rec

    def evaluate_full_session_chronological(
        self,
        participant_id: str,
        session_id: str,
        channel_mode: str,
        tta_enabled: bool,
        include_waveforms: bool = False,
    ) -> dict[str, Any]:
        """
        Runs a fresh chronological trial-by-trial evaluation (t = 1..N) over the entire
        selected session and dynamically computes session metrics (ArtGate90 & All-Trials)
        plus a NEUROLINK website `ReplaySource`-compatible object.
        """
        self.load_all()
        entry, fmodel = self.resolve_calib_model(participant_id, session_id, channel_mode, tta_enabled)
        raw_key = f"{entry['subject']}__{entry['session']}"
        if raw_key not in self.raw_sessions_map:
            raise FileNotFoundError(f"Local EEG session cache not found for {raw_key}")

        sdata = self.raw_sessions_map[raw_key]
        on = sdata["on"]
        yo = on["y"]
        eog_arr = on["eog"]
        ts_arr = on["timestamps"]
        xo_band = on["bands"][fmodel.band_name]

        engine = StatefulOnlineTTASession(fmodel, tta_override=tta_enabled)
        predictions: list[dict[str, Any]] = []
        replay_frames: list[dict[str, Any]] = []

        for t_idx in range(len(yo)):
            rec = engine.step(
                xo_band[t_idx],
                eog_ptp_uv=float(eog_arr[t_idx]),
                true_label_int=int(yo[t_idx]),
                trial_id=t_idx + 1,
                timestamp_s=float(ts_arr[t_idx]),
                is_band_filtered=True,
            )
            if include_waveforms:
                rec["waveform"] = self.extract_waveform_snippet(xo_band[t_idx], fmodel.active_channels)
            predictions.append(rec)

            # Build downsampled EEGFrame samples for website ReplaySource
            # Take 10 representative samples per trial across active channels
            for sample_offset in range(0, 500, 50):
                ch_dict = {}
                for ch_i, ch_name in zip(fmodel.ch_idx, fmodel.active_channels):
                    ch_dict[ch_name] = round(float(xo_band[t_idx, ch_i, sample_offset]), 3)
                replay_frames.append({
                    "timestamp": round(float(ts_arr[t_idx]) + sample_offset / FS, 3),
                    "channels": ch_dict,
                })

        preds_int = np.array([1 if p["predicted_direction"] == "RIGHT" else 0 for p in predictions], dtype=int)
        probs_r = np.array([p["probability_right"] for p in predictions], dtype=np.float64)
        clean_mask = np.array([p["quality"]["is_clean"] for p in predictions], dtype=bool)
        latencies = np.array([p["latency_ms"] for p in predictions], dtype=np.float64)

        def calc_metrics(y_sub: np.ndarray, pred_sub: np.ndarray, prob_sub: np.ndarray) -> dict[str, float]:
            if len(y_sub) == 0:
                return {"balanced_accuracy_pct": 0.0, "accuracy_pct": 0.0, "roc_auc": 0.5}
            bacc = float(balanced_accuracy_score(y_sub, pred_sub) * 100.0)
            acc = float(accuracy_score(y_sub, pred_sub) * 100.0)
            auc = float(roc_auc_score(y_sub, prob_sub)) if len(np.unique(y_sub)) > 1 else 0.5
            return {
                "balanced_accuracy_pct": round(bacc, 2),
                "accuracy_pct": round(acc, 2),
                "roc_auc": round(auc, 4),
            }

        metrics_90 = calc_metrics(yo[clean_mask], preds_int[clean_mask], probs_r[clean_mask])
        metrics_all = calc_metrics(yo, preds_int, probs_r)
        spec = PARTICIPANT_SPECS.get(entry["subject"], {})

        return {
            "participant_id": entry["subject"],
            "korean_name": spec.get("korean_name", entry["subject"]),
            "session_id": session_id,
            "resolved_session_name": entry["session"],
            "date": entry["date"],
            "is_golden_50": bool(entry.get("is_golden_50", False)),
            "channel_mode": fmodel.channel_mode_key,
            "montage": fmodel.montage_name,
            "n_channels": len(fmodel.ch_idx),
            "active_channels": fmodel.active_channels,
            "tta_enabled": bool(tta_enabled),
            "model_id": spec.get("model_id", f"{entry['subject'].lower()}-calib20"),
            "model_name": f"{spec.get('model_name', 'Calib20 Reg-CSP + sLDA')} ({fmodel.montage_name})",
            "total_trials": int(len(yo)),
            "clean_trials_artgate90": int(np.sum(clean_mask)),
            "artifact_gated_trials": int(np.sum(~clean_mask)),
            "live_in_game_accuracy_pct": round(float(entry["live_acc"]), 2) if not np.isnan(entry["live_acc"]) else None,
            "computed_metrics_artgate90": metrics_90,
            "computed_metrics_all_trials": metrics_all,
            "mean_latency_ms": round(float(np.mean(latencies)), 4),
            "predictions": predictions,
            "replay_source": {
                "kind": "recorded",
                "sampleRateHz": int(FS),
                "predictions": [
                    {
                        "trialId": p["trialId"],
                        "timestamp": p["timestamp"],
                        "trueLabel": p["trueLabel"],
                        "predictedLabel": p["predictedLabel"],
                        "score": p["score"],
                        "modelId": p["modelId"],
                        "channelSet": p["channelSet"],
                    }
                    for p in predictions
                ],
                "frames": replay_frames,
            },
        }

    def calibrate_custom_or_recorded_session(
        self,
        participant_id: str,
        session_id: str,
        channel_mode: str,
        tta_enabled: bool,
        calibration_epochs: list[list[list[float]]] | None = None,
        calibration_labels: list[str | int] | None = None,
        client_key: str = "rest",
    ) -> dict[str, Any]:
        """
        Runs the Same-Day Calib20 + Multi-Crop calibration protocol:
        - If `calibration_epochs` (N_cal, 16, 500) and `calibration_labels` are provided,
          filters raw EEG (60Hz notch + bandpass), extracts multi-crop windows, fits
          Regularized CSP + sLDA and reference covariance `R_cal`, and initializes a live TTA session.
        - Otherwise, resets and initializes the pre-calibrated Calib20 session state.
        """
        t0 = time.perf_counter()
        self.load_all()
        subj = participant_id.upper()
        spec = PARTICIPANT_SPECS.get(subj, PARTICIPANT_SPECS["WMJ"])

        if calibration_epochs is not None and calibration_labels is not None:
            raw_cal = np.asarray(calibration_epochs, dtype=np.float64)
            if raw_cal.ndim != 3:
                raise ValueError(f"Expected 3D calibration_epochs (N, C, T), got {raw_cal.shape}")
            yc = np.array(
                [1 if str(lbl).strip().upper() in ("1", "RIGHT") else 0 for lbl in calibration_labels],
                dtype=np.int64,
            )
            band_name = spec.get("online_band", "himu")
            notched = sosfilt(SOS_NOTCH, raw_cal, axis=2)
            xc_band = sosfilt(ONLINE_BAND_SOS[band_name], notched, axis=2)
            eog_cal = np.max(np.ptp(notched[:, IDX_EOG, : min(375, notched.shape[2])], axis=2), axis=1)
            thr_90 = float(np.percentile(eog_cal, 90.0))

            cm = channel_mode.strip().lower()
            if cm == "16ch":
                mname = "16ch_NoCAR"
            elif cm == "5ch":
                mname = "5ch_PM_NoCAR"
            elif cm == "7ch":
                mname = "7ch_PM_NoCAR"
            else:
                mname = spec.get("optimal_montage", "7ch_PM_NoCAR")
                if mname not in ("16ch_NoCAR", "7ch_PM_NoCAR", "7ch_PM_LocCAR", "5ch_PM_NoCAR", "5ch_PM_LocCAR"):
                    mname = "7ch_PM_NoCAR"

            fitted = Calib20FittedModel.fit_from_calibration(
                subject=subj,
                session=session_id,
                date="custom",
                channel_mode_key=cm,
                montage_name=mname,
                band_name=band_name,
                win_name="W_1.5s_Multi",
                reg=0.05,
                use_ea=tta_enabled,
                use_center=tta_enabled,
                xc_band_16=xc_band,
                yc=yc,
                thr_90_uv=thr_90,
            )
            state_key = f"{client_key}::{subj}::{session_id}::{cm}::{tta_enabled}"
            self.active_online_states[state_key] = StatefulOnlineTTASession(fitted, tta_override=tta_enabled)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "status": "CALIBRATED_FROM_RAW_EPOCHS",
                "participant_id": subj,
                "session_id": session_id,
                "channel_mode": cm,
                "montage": mname,
                "active_channels": fitted.active_channels,
                "tta_enabled": tta_enabled,
                "n_calibration_trials": int(len(yc)),
                "artgate90_threshold_uv": round(thr_90, 2),
                "calibration_latency_ms": round(elapsed_ms, 2),
            }

        entry, engine = self.get_or_create_online_state(
            subj, session_id, channel_mode, tta_enabled, client_key=client_key, reset=True
        )
        fmodel = engine.model
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "status": "INITIALIZED_CALIB20_SESSION",
            "participant_id": entry["subject"],
            "session_id": session_id,
            "resolved_session_name": entry["session"],
            "date": entry["date"],
            "is_golden_50": bool(entry.get("is_golden_50", False)),
            "channel_mode": fmodel.channel_mode_key,
            "montage": fmodel.montage_name,
            "n_channels": len(fmodel.ch_idx),
            "active_channels": fmodel.active_channels,
            "tta_enabled": tta_enabled,
            "n_calibration_trials": fmodel.n_calib_trials,
            "n_online_trials": fmodel.n_online_trials,
            "artgate90_threshold_uv": round(fmodel.thr_90_uv, 2),
            "calibration_latency_ms": round(elapsed_ms, 3),
        }

    def evaluate_cohort_50_sessions_dynamic(self, golden_only: bool = True) -> dict[str, Any]:
        """
        Dynamically runs chronological trial-by-trial inference across all 50 Golden Sessions
        (or all 77 16ch calibrated sessions if `golden_only=False`) using `StatefulOnlineTTASession`.
        Nothing is hardcoded: every session's accuracy and AUC is computed live from the EEG trials.
        """
        t0 = time.perf_counter()
        self.load_all()
        rows = []
        for key, entry in self.online_models_map.items():
            if entry.get("is_7ch", False):
                continue
            if golden_only and not entry.get("is_golden_50", False):
                continue
            if key not in self.raw_sessions_map:
                continue

            sdata = self.raw_sessions_map[key]
            on = sdata["on"]
            yo = on["y"]
            eog = on["eog"]
            ts_arr = on["timestamps"]
            m90 = eog <= entry["thr_90_uv"]

            row = {
                "subject": entry["subject"],
                "session": entry["session"],
                "date": entry["date"],
                "live_acc": float(entry["live_acc"]),
            }
            for regime_tag, m_key in [
                ("16ch_only", "16ch__tta_off"),
                ("16ch_tta", "16ch__tta_on"),
                ("low_only", "low__tta_off"),
                ("low_tta", "low__tta_on"),
            ]:
                fmodel: Calib20FittedModel = entry["models"][m_key]
                engine = StatefulOnlineTTASession(fmodel)
                xo_band = on["bands"][fmodel.band_name]
                preds, probs = [], []
                for t_idx in range(len(yo)):
                    rec = engine.step(
                        xo_band[t_idx],
                        eog_ptp_uv=float(eog[t_idx]),
                        true_label_int=int(yo[t_idx]),
                        trial_id=t_idx + 1,
                        timestamp_s=float(ts_arr[t_idx]),
                        is_band_filtered=True,
                    )
                    preds.append(1 if rec["predicted_direction"] == "RIGHT" else 0)
                    probs.append(rec["probability_right"])
                ye = yo[m90]
                pe_pred = np.array(preds, dtype=int)[m90]
                pe_prob = np.array(probs, dtype=np.float64)[m90]
                row[f"{regime_tag}_bacc"] = float(balanced_accuracy_score(ye, pe_pred) * 100.0)
                row[f"{regime_tag}_auc"] = float(roc_auc_score(ye, pe_prob)) if len(np.unique(ye)) > 1 else 0.5
            rows.append(row)

        df = pd.DataFrame(rows)
        per_subject = []
        for subj in ("WMJ", "OYJ", "KGE", "KHY"):
            d = df[df["subject"] == subj]
            if d.empty:
                continue
            t_stat, p_val = ttest_rel(d["low_tta_bacc"], d["16ch_only_bacc"]) if len(d) > 1 else (0.0, 1.0)
            per_subject.append({
                "participant_id": subj,
                "korean_name": PARTICIPANT_SPECS[subj]["korean_name"],
                "n_sessions": int(len(d)),
                "live_game_bacc_pct": round(float(d["live_acc"].mean()), 2),
                "16ch_only_bacc_pct": round(float(d["16ch_only_bacc"].mean()), 2),
                "16ch_tta_bacc_pct": round(float(d["16ch_tta_bacc"].mean()), 2),
                "lowch_only_bacc_pct": round(float(d["low_only_bacc"].mean()), 2),
                "lowch_tta_bacc_pct": round(float(d["low_tta_bacc"].mean()), 2),
                "gain_vs_live_pct_pt": round(float(d["low_tta_bacc"].mean() - d["live_acc"].mean()), 2),
                "gain_vs_16ch_pct_pt": round(float(d["low_tta_bacc"].mean() - d["16ch_only_bacc"].mean()), 2),
                "16ch_only_auc": round(float(d["16ch_only_auc"].mean()), 3),
                "lowch_tta_auc": round(float(d["low_tta_auc"].mean()), 3),
                "paired_t_vs_16ch": round(float(t_stat), 3),
                "paired_p_vs_16ch": round(float(p_val), 4),
            })

        df_sub = pd.DataFrame(per_subject)
        unrounded_means = df.groupby("subject")[["live_acc", "16ch_only_bacc", "16ch_tta_bacc", "low_only_bacc", "low_tta_bacc"]].mean().mean()
        t_16, p_16 = ttest_rel(df["low_tta_bacc"], df["16ch_only_bacc"])
        w_16, pw_16 = wilcoxon(df["low_tta_bacc"], df["16ch_only_bacc"])
        t_live, p_live = ttest_rel(df["low_tta_bacc"], df["live_acc"])
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "cohort_type": "50_Golden_Sessions" if golden_only else "All_77_16ch_Calibrated_Sessions",
            "total_sessions_evaluated": int(len(df)),
            "computation_latency_ms": round(elapsed_ms, 2),
            "per_subject": per_subject,
            "cohort_grand_mean": {
                "live_game_bacc_pct": round(float(unrounded_means["live_acc"]), 2),
                "16ch_only_bacc_pct": round(float(unrounded_means["16ch_only_bacc"]), 2),
                "16ch_tta_bacc_pct": round(float(unrounded_means["16ch_tta_bacc"]), 2),
                "lowch_only_bacc_pct": round(float(unrounded_means["low_only_bacc"]), 2),
                "lowch_tta_bacc_pct": round(float(unrounded_means["low_tta_bacc"]), 2),
                "gain_vs_live_pct_pt": round(float(unrounded_means["low_tta_bacc"] - unrounded_means["live_acc"]), 2),
                "gain_vs_16ch_pct_pt": round(float(unrounded_means["low_tta_bacc"] - unrounded_means["16ch_only_bacc"]), 2),
                "paired_t_vs_16ch": round(float(t_16), 3),
                "paired_p_vs_16ch": float(p_16),
                "wilcoxon_p_vs_16ch": float(pw_16),
                "paired_t_vs_live": round(float(t_live), 3),
                "paired_p_vs_live": float(p_live),
            },
        }


# Singleton instance for FastAPI app
inference_manager = NeurolinkInferenceManager()
