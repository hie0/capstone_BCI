# -*- coding: utf-8 -*-
"""
Actual Research Signal Processing, Calibration, Models, and Causal TTA Protocol
================================================================================
Directly implements the exact mathematical pipelines used in the final presentation:
1. 50-Session Online Evaluation (`run_4subj_calib_online_master.py`):
   - Same-Day 20-Trial Calibration (`Calib20`) + Multi-Crop Ensemble (`W_1.5s_Multi`, `W_1.0s_Dual`, `W_2.0s_Single`)
   - Regularized CSP (`reg=0.05` / `0.15`, `n_comp=4`) + Shrinkage LDA (`solver="lsqr", shrinkage="auto"`)
   - Causal Euclidean Alignment (`CausalEA`: warm-started with `R_init = r_cal * 8.0`, `eye_p = 0.2 * I / C`)
   - Causal Logit Centering (`CausalLogitCenter`: running bias removal with `prior_n = 3.0`)
   - Unsupervised Pre-Trial Artifact Gate (`ArtGate90`: frontal/temporal EOG peak-to-peak <= 90th percentile)

2. 4-Subject Offline Evaluation (`run_8core_turbo_boost.py` & `exp7_wmj_and_clean_max_boost.py`):
   - WMJ: `7ch_PM_NoCAR` / `5ch_Core_NoCAR`, `CSP_WelchPSD_sLDA` & `SuperHybrid_TS_CSP_ERD`
   - KGE: `5ch_PM_NoCAR` / `7ch_PM_LocCAR`, `Riemann_TS_sLDA` & `Riemann_TS_LR` (OAS + Ensure-SPD + Log-Euclidean TS)
   - OYJ: `5ch_PM_NoCAR` / `6ch_PM_LocCAR` / `7ch_PM_LocCAR`, `SuperHybrid_TS_CSP_ERD` (0.55*RiemannTS + 0.45*CSP_PSD_ERD)
   - KHY: `6ch_PM_LocCAR` / `7ch_PM_LocCAR`, `ArtGate90` + `broad_8_35` + Ensure-SPD `Riemann_TS_LR` / `SuperHybrid_TS_CSP_ERD`
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


def resolve_data_root() -> Path:
    """Resolves local EEG data directory from BCI_DATA_ROOT env var, gitignored local_cache/data_root.txt, or ./data."""
    env_val = os.environ.get("BCI_DATA_ROOT", "").strip()
    if env_val:
        return Path(env_val)
    hint_file = Path(__file__).resolve().parent / "local_cache" / "data_root.txt"
    if hint_file.exists():
        txt = hint_file.read_text(encoding="utf-8").strip()
        if txt:
            return Path(txt)
    return Path(__file__).resolve().parent.parent / "data"
from scipy.linalg import eigh
from scipy.signal import butter, iirnotch, sosfilt, tf2sos
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import MinMaxScaler, RobustScaler, StandardScaler

FS: float = 250.0

ELECTRODE_NAMES_16: list[str] = [
    "Fp1", "Fp2", "F7", "F3", "F4", "F8", "T7", "C3",
    "Cz", "C4", "T8", "P7", "Pz", "P8", "O1", "O2",
]
CH_COLS: list[str] = [f"ch{i}" for i in range(1, 17)]
IDX_EOG: list[int] = [0, 1, 2, 5]  # Fp1, Fp2, F7, F8
HOMOLOGOUS_16: list[tuple[int, int]] = [
    (0, 1), (2, 5), (3, 4), (6, 10), (7, 9), (11, 13), (14, 15)
]

# Online montages from run_4subj_calib_online_master.py
ONLINE_MONTAGES: dict[str, tuple[list[int], bool]] = {
    "16ch_NoCAR": (list(range(16)), False),
    "16ch_CAR": (list(range(16)), True),
    "7ch_PM_NoCAR": ([3, 4, 7, 8, 9, 11, 13], False),
    "7ch_PM_LocCAR": ([3, 4, 7, 8, 9, 11, 13], True),
    "7ch_T_NoCAR": ([6, 7, 8, 9, 10, 11, 13], False),
    "6ch_PM_NoCAR": ([3, 4, 7, 8, 9, 12], False),
    "5ch_PM_NoCAR": ([3, 4, 7, 8, 9], False),
    "5ch_PM_LocCAR": ([3, 4, 7, 8, 9], True),
    "5ch_Core_NoCAR": ([7, 8, 9, 11, 13], False),
}

# Offline montages from run_8core_turbo_boost.py
OFFLINE_MONTAGES: dict[str, tuple[list[int], str]] = {
    "16ch_NoCAR": (list(range(16)), "none"),
    "16ch_CAR": (list(range(16)), "global_car"),
    "8ch_PM_Par_LocCAR": ([3, 4, 7, 8, 9, 11, 12, 13], "local_car"),
    "7ch_PM_NoCAR": ([3, 4, 7, 8, 9, 11, 13], "none"),
    "7ch_PM_LocCAR": ([3, 4, 7, 8, 9, 11, 13], "local_car"),
    "7ch_T_NoCAR": ([6, 7, 8, 9, 10, 11, 13], "none"),
    "7ch_T_LocCAR": ([6, 7, 8, 9, 10, 11, 13], "local_car"),
    "6ch_PM_LocCAR": ([3, 4, 7, 9, 11, 13], "local_car"),
    "5ch_PM_NoCAR": ([3, 4, 7, 8, 9], "none"),
    "5ch_Core_NoCAR": ([6, 7, 8, 9, 10], "none"),
}

# Multi-crop subwindows (samples at 250 Hz) from run_4subj_calib_online_master.py
ONLINE_CROPS_MAP: dict[str, list[ tuple[int, int] ]] = {
    "W_1.5s_Multi": [(0, 250), (62, 312), (125, 375)],
    "W_1.0s_Dual": [(0, 125), (125, 250)],
    "W_2.0s_Single": [(0, 500)],
}

# Poster 50 Golden Sessions Date Filter per Subject
POSTER_GOLDEN_DATES: dict[str, list[str]] = {
    "WMJ": ["0928", "0930", "1001", "1007"],          # 13 sessions
    "OYJ": ["0929", "0930", "1002", "1007"],          # 9 sessions
    "KGE": ["0928", "0930", "1001", "1007"],          # 13 sessions
    "KHY": ["0928", "0930", "1001", "1006", "1008"],  # 15 sessions
}

# Participant metadata matching NEUROLINK website & final presentation
PARTICIPANT_SPECS: dict[str, dict[str, Any]] = {
    "WMJ": {
        "participant_id": "WMJ",
        "korean_name": "Participant WMJ",
        "optimal_channel_mode": "7ch",
        "optimal_montage": "7ch_PM_NoCAR",
        "optimal_channels": ["F3", "F4", "C3", "Cz", "C4", "P7", "P8"],
        "model_id": "wmj-reg-csp",
        "model_name": "Regularized CSP + Welch PSD + sLDA",
        "online_band": "himu",
        "offline_band": "fb_wmj",
    },
    "KGE": {
        "participant_id": "KGE",
        "korean_name": "Participant KGE",
        "optimal_channel_mode": "5ch",
        "optimal_montage": "5ch_PM_NoCAR",
        "optimal_channels": ["F3", "F4", "C3", "Cz", "C4"],
        "model_id": "kge-oas-ts",
        "model_name": "OAS + Log-Euclidean Riemann TS + sLDA/LR",
        "online_band": "extmu",
        "offline_band": "hi_mu_10_15",
    },
    "OYJ": {
        "participant_id": "OYJ",
        "korean_name": "Participant OYJ",
        "optimal_channel_mode": "5ch",
        "optimal_montage": "5ch_PM_NoCAR",
        "optimal_channels": ["F3", "F4", "C3", "Cz", "C4"],
        "model_id": "oyj-hybrid",
        "model_name": "SuperHybrid (0.55 Riemann TS + 0.45 Reg-CSP/ERD)",
        "online_band": "himu",
        "offline_band": "hi_mu_10_15",
    },
    "KHY": {
        "participant_id": "KHY",
        "korean_name": "Participant KHY",
        "optimal_channel_mode": "7ch",
        "optimal_montage": "6ch_PM_LocCAR",
        "optimal_channels": ["F3", "F4", "C3", "Cz", "C4", "P7", "P8"],
        "model_id": "khy-spd-ts",
        "model_name": "ArtGate90 + Ensure-SPD OAS + Riemann TS + sLDA",
        "online_band": "extmu",
        "offline_band": "broad_8_35",
    },
}


# ---------------------------------------------------------------------------
# Filter Design
# ---------------------------------------------------------------------------
def make_band_sos(low_hz: float, high_hz: float, order: int = 4, fs: float = FS) -> np.ndarray:
    return butter(order, [low_hz, high_hz], btype="bandpass", fs=fs, output="sos")


_b_notch, _a_notch = iirnotch(60.0, 30.0, fs=FS)
SOS_NOTCH: np.ndarray = tf2sos(_b_notch, _a_notch)

ONLINE_BAND_SOS: dict[str, np.ndarray] = {
    "mu": make_band_sos(8.0, 13.0),
    "extmu": make_band_sos(8.0, 15.0),
    "himu": make_band_sos(10.0, 15.0),
}

OFFLINE_BAND_DEFS: dict[str, tuple[float, float, np.ndarray]] = {
    "mu_8_13": (8.0, 13.0, make_band_sos(8.0, 13.0)),
    "extmu_9_14": (9.0, 14.0, make_band_sos(9.0, 14.0)),
    "hi_mu_10_15": (10.0, 15.0, make_band_sos(10.0, 15.0)),
    "low_beta_12_20": (12.0, 20.0, make_band_sos(12.0, 20.0)),
    "beta_16_26": (16.0, 26.0, make_band_sos(16.0, 26.0)),
    "broad_8_35": (8.0, 35.0, make_band_sos(8.0, 35.0)),
}


def ch_indices_to_names(ch_idx: list[int]) -> list[str]:
    return [ELECTRODE_NAMES_16[i] for i in ch_idx if 0 <= i < len(ELECTRODE_NAMES_16)]


def compute_cov_condition_log10(cov: np.ndarray) -> float:
    vals = eigh(0.5 * (cov + cov.T), eigvals_only=True)
    vals = np.maximum(vals, 1e-15)
    return float(np.log10(np.max(vals) / np.min(vals)))


# ---------------------------------------------------------------------------
# Online Protocol Primitives (Exact match to run_4subj_calib_online_master.py)
# ---------------------------------------------------------------------------
def causal_ea_batch(X_seq: np.ndarray, R_init: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Exact batch Causal Euclidean Alignment from run_4subj_calib_online_master.py."""
    n, c, t = X_seq.shape
    covs = np.einsum("nct,ndt->ncd", X_seq, X_seq) / max(t - 1, 1)
    tr_v = np.trace(covs, axis1=1, axis2=2)[:, None, None]
    covs = covs / np.maximum(tr_v, 1e-18) + 1e-6 * np.eye(c)
    out = np.empty_like(X_seq, dtype=np.float64)
    r_sum = R_init.copy() * 8.0 if R_init is not None else np.zeros((c, c), dtype=np.float64)
    w0 = 8.0 if R_init is not None else 0.2
    eye_p = 0.2 * (np.eye(c, dtype=np.float64) / c)
    for i in range(n):
        r_sum += covs[i]
        rm = (eye_p + r_sum) / (w0 + i + 1.0)
        vals, vecs = eigh(0.5 * (rm + rm.T))
        w_mat = (vecs * (1.0 / np.sqrt(np.maximum(vals, 1e-10)))) @ vecs.T
        out[i] = w_mat @ X_seq[i]
    return out, np.mean(covs, axis=0)


def causal_ea_single_step(
    x_crop: np.ndarray,
    r_sum: np.ndarray,
    step_idx: int,
    w0: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Single-trial chronological step of CausalEA.
    Returns (x_whitened, updated_r_sum, rm_current).
    Exactly matches iteration `i = step_idx` of `causal_ea_batch`.
    """
    c, t = x_crop.shape
    cov = (x_crop @ x_crop.T) / max(t - 1, 1)
    tr_v = float(np.trace(cov))
    cov = cov / max(tr_v, 1e-18) + 1e-6 * np.eye(c, dtype=np.float64)
    r_sum_new = r_sum + cov
    eye_p = 0.2 * (np.eye(c, dtype=np.float64) / c)
    rm = (eye_p + r_sum_new) / (w0 + step_idx + 1.0)
    vals, vecs = eigh(0.5 * (rm + rm.T))
    w_mat = (vecs * (1.0 / np.sqrt(np.maximum(vals, 1e-10)))) @ vecs.T
    x_aligned = w_mat @ x_crop
    return x_aligned, r_sum_new, rm


def causal_center_batch(logits: np.ndarray, prior_n: float = 3.0, init_bias: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Exact batch Causal Logit Centering from run_4subj_calib_online_master.py."""
    centered = np.empty_like(logits, dtype=np.float64)
    s = float(init_bias * prior_n)
    for i in range(len(logits)):
        s += float(logits[i])
        centered[i] = logits[i] - s / (prior_n + i + 1.0)
    probs = 1.0 / (1.0 + np.exp(-np.clip(centered, -20.0, 20.0)))
    return centered, probs


def fit_csp_slda(X_tr: np.ndarray, y_tr: np.ndarray, reg: float = 0.05) -> tuple[np.ndarray, LinearDiscriminantAnalysis]:
    """
    Fits Regularized CSP spatial filters `W` and Shrinkage LDA `clf`
    matching `fast_csp_lda_logits` in `run_4subj_calib_online_master.py`.
    """
    n, c, t = X_tr.shape
    covs = np.einsum("nct,ndt->ncd", X_tr, X_tr) / max(t - 1, 1)
    tr_v = np.trace(covs, axis1=1, axis2=2)[:, None, None]
    covs = covs / np.maximum(tr_v, 1e-18)
    c0 = np.mean(covs[y_tr == 0], axis=0)
    c1 = np.mean(covs[y_tr == 1], axis=0)
    eye = np.eye(c, dtype=np.float64)
    c0 = (1.0 - reg) * c0 + reg * (np.trace(c0) / c) * eye
    c1 = (1.0 - reg) * c1 + reg * (np.trace(c1) / c) * eye
    vals, vecs = eigh(c0, c0 + c1)
    n_comp = min(4, c - 1 if c > 1 else 1)
    k = max(n_comp // 2, 1)
    idx = np.concatenate([np.arange(k), np.arange(c - k, c)])
    W = vecs[:, idx].T
    proj_tr = np.einsum("kc,nct->nkt", W, X_tr)
    p_tr = np.mean(proj_tr ** 2, axis=2)
    f_tr = np.log(p_tr / np.sum(p_tr, axis=1, keepdims=True) + 1e-18)
    clf = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(f_tr, y_tr)
    return W, clf


@dataclass
class Calib20FittedModel:
    """
    Serializable fitted state of the Same-Day Calib20 + Multi-Crop + CausalEA + sLDA model.
    Exported via joblib without raw EEG waveforms.
    """
    subject: str
    session: str
    date: str
    channel_mode_key: str  # "16ch", "low", "7ch", "5ch"
    montage_name: str
    ch_idx: list[int]
    active_channels: list[str]
    use_car: bool
    band_name: str
    win_name: str
    crop_slices: list[tuple[int, int]]
    reg: float
    use_ea: bool
    use_center: bool
    W: np.ndarray  # (n_comp, C) CSP spatial filter matrix
    clf: LinearDiscriminantAnalysis
    r_cal_crops: list[np.ndarray]  # Reference covariance per crop window from Calib20
    thr_90_uv: float  # ArtGate90 frontal/temporal EOG threshold (uV)
    live_game_acc: float
    n_calib_trials: int
    n_online_trials: int

    @classmethod
    def fit_from_calibration(
        cls,
        subject: str,
        session: str,
        date: str,
        channel_mode_key: str,
        montage_name: str,
        band_name: str,
        win_name: str,
        reg: float,
        use_ea: bool,
        use_center: bool,
        xc_band_16: np.ndarray,
        yc: np.ndarray,
        thr_90_uv: float,
        live_game_acc: float = 0.0,
        n_online_trials: int = 0,
    ) -> "Calib20FittedModel":
        ch_idx, use_car = ONLINE_MONTAGES[montage_name]
        crop_slices = ONLINE_CROPS_MAP[win_name]
        xc_l = []
        r_cal_crops = []
        for s0, s1 in crop_slices:
            xc = xc_band_16[:, ch_idx, s0:s1].copy()
            if use_car:
                xc -= xc.mean(axis=1, keepdims=True)
            if use_ea:
                xc, r_cal = causal_ea_batch(xc, R_init=None)
            else:
                _, r_cal = causal_ea_batch(xc, R_init=None)
            xc_l.append(xc)
            r_cal_crops.append(r_cal)

        Xtr = np.concatenate(xc_l, axis=0)
        ytr = np.concatenate([yc] * len(crop_slices), axis=0)
        W, clf = fit_csp_slda(Xtr, ytr, reg=reg)
        return cls(
            subject=subject,
            session=session,
            date=date,
            channel_mode_key=channel_mode_key,
            montage_name=montage_name,
            ch_idx=list(ch_idx),
            active_channels=ch_indices_to_names(list(ch_idx)),
            use_car=use_car,
            band_name=band_name,
            win_name=win_name,
            crop_slices=list(crop_slices),
            reg=float(reg),
            use_ea=bool(use_ea),
            use_center=bool(use_center),
            W=W,
            clf=clf,
            r_cal_crops=r_cal_crops,
            thr_90_uv=float(thr_90_uv),
            live_game_acc=float(live_game_acc),
            n_calib_trials=int(len(yc)),
            n_online_trials=int(n_online_trials),
        )


class StatefulOnlineTTASession:
    """
    Stateful chronological online inference engine for a session.
    Processes trials t = 0, 1, 2, ... in strict temporal order, updating CausalEA
    running covariance and CausalLogitCenter running bias without any future peeking.
    """

    def __init__(self, model: Calib20FittedModel, tta_override: bool | None = None):
        self.model = model
        self.tta_enabled: bool = model.use_ea if tta_override is None else bool(tta_override)
        self.reset()

    def reset(self) -> None:
        self.step_idx: int = 0
        self.r_sum_crops: list[np.ndarray] = []
        for r_cal in self.model.r_cal_crops:
            if r_cal is not None:
                self.r_sum_crops.append(r_cal.copy() * 8.0)
            else:
                c = len(self.model.ch_idx)
                self.r_sum_crops.append(np.zeros((c, c), dtype=np.float64))
        self.w0: float = 8.0
        self.prior_n: float = 3.0
        self.logit_sum: float = 0.0
        self.history: list[dict[str, Any]] = []

    def step(
        self,
        x_epoch: np.ndarray,
        eog_ptp_uv: float | None = None,
        true_label_int: int | None = None,
        trial_id: int | None = None,
        timestamp_s: float | None = None,
        is_band_filtered: bool = True,
    ) -> dict[str, Any]:
        """
        Runs chronological single-trial inference on `x_epoch` of shape `(16, T)` or `(C, T)` (T >= 375, typically 500).
        If `is_band_filtered=False`, applies 60 Hz IIR notch + subject/model bandpass first.
        """
        t_start = time.perf_counter()

        x_in = np.asarray(x_epoch, dtype=np.float64)
        if x_in.ndim != 2:
            raise ValueError(f"Expected 2D EEG array (C, T), got shape {x_in.shape}")

        # Ensure (C, T) orientation
        if x_in.shape[0] > x_in.shape[1] and x_in.shape[1] in (16, len(self.model.ch_idx)):
            x_in = x_in.T

        # Compute EOG peak-to-peak if not pre-supplied and 16 channels are provided
        if not is_band_filtered:
            notched = sosfilt(SOS_NOTCH, x_in, axis=1)
            if eog_ptp_uv is None and x_in.shape[0] == 16:
                seg_len = min(375, notched.shape[1])
                eog_ptp_uv = float(np.max(np.ptp(notched[IDX_EOG, :seg_len], axis=1)))
            band_sos = ONLINE_BAND_SOS.get(self.model.band_name, ONLINE_BAND_SOS["himu"])
            x_band = sosfilt(band_sos, notched, axis=1)
        else:
            x_band = x_in
            if eog_ptp_uv is None:
                if x_in.shape[0] == 16:
                    seg_len = min(375, x_in.shape[1])
                    eog_ptp_uv = float(np.max(np.ptp(x_in[IDX_EOG, :seg_len], axis=1)))
                else:
                    eog_ptp_uv = float(np.max(np.ptp(x_in, axis=1)))

        # Select montage channels if 16ch input provided
        if x_band.shape[0] == 16:
            x_montage = x_band[self.model.ch_idx, :].copy()
        elif x_band.shape[0] == len(self.model.ch_idx):
            x_montage = x_band.copy()
        else:
            raise ValueError(
                f"Expected 16 channels or {len(self.model.ch_idx)} montage channels, got {x_band.shape[0]}"
            )

        # Multi-crop evaluation
        crop_logits: list[float] = []
        last_rm: np.ndarray | None = None

        for crop_idx, (s0, s1) in enumerate(self.model.crop_slices):
            s1_eff = min(s1, x_montage.shape[1])
            s0_eff = min(s0, max(0, s1_eff - 50))
            xc = x_montage[:, s0_eff:s1_eff].copy()
            if self.model.use_car:
                xc -= xc.mean(axis=0, keepdims=True)

            if self.tta_enabled:
                xc_proc, r_sum_updated, rm = causal_ea_single_step(
                    xc, self.r_sum_crops[crop_idx], self.step_idx, self.w0
                )
                self.r_sum_crops[crop_idx] = r_sum_updated
                last_rm = rm
            else:
                xc_proc = xc
                c, t_len = xc.shape
                cov = (xc @ xc.T) / max(t_len - 1, 1)
                tr_v = float(np.trace(cov))
                last_rm = cov / max(tr_v, 1e-18) + 1e-6 * np.eye(c)

            proj = self.model.W @ xc_proc  # (n_comp, t_crop)
            p_var = np.mean(proj ** 2, axis=1)
            f_vec = np.log(p_var / (np.sum(p_var) + 1e-18) + 1e-18)[None, :]
            logit_k = float(self.model.clf.decision_function(f_vec)[0])
            crop_logits.append(logit_k)

        raw_logit = float(np.mean(crop_logits))

        if self.tta_enabled:
            self.logit_sum += raw_logit
            running_bias = self.logit_sum / (self.prior_n + self.step_idx + 1.0)
            calibrated_logit = raw_logit - running_bias
        else:
            running_bias = 0.0
            calibrated_logit = raw_logit

        prob_right = float(1.0 / (1.0 + np.exp(-np.clip(calibrated_logit, -20.0, 20.0))))
        pred_int = 1 if prob_right >= 0.5 else 0
        pred_dir = "RIGHT" if pred_int == 1 else "LEFT"
        true_dir = ("RIGHT" if true_label_int == 1 else "LEFT") if true_label_int in (0, 1) else None
        is_correct = (pred_int == true_label_int) if true_label_int in (0, 1) else None

        is_clean = bool(eog_ptp_uv <= self.model.thr_90_uv)
        cond_log10 = compute_cov_condition_log10(last_rm) if last_rm is not None else 0.0

        latency_ms = float((time.perf_counter() - t_start) * 1000.0)
        current_trial_number = trial_id if trial_id is not None else (self.step_idx + 1)
        current_ts = timestamp_s if timestamp_s is not None else float(self.step_idx * 2.0)

        self.step_idx += 1

        spec = PARTICIPANT_SPECS.get(self.model.subject, {})
        record = {
            "trial_id": int(current_trial_number),
            "trialId": int(current_trial_number),
            "step_index": int(self.step_idx),
            "timestamp": float(current_ts),
            "participant_id": self.model.subject,
            "session_id": self.model.session,
            "model_id": f"{self.model.subject.lower()}-calib20-csp-slda",
            "modelId": f"{self.model.subject.lower()}-calib20-csp-slda",
            "model_name": f"Calib20 · Regularized CSP + sLDA ({self.model.montage_name})",
            "channel_mode": self.model.channel_mode_key,
            "channelSet": self.model.channel_mode_key,
            "montage": self.model.montage_name,
            "n_channels": len(self.model.ch_idx),
            "active_channels": self.model.active_channels,
            "tta_enabled": self.tta_enabled,
            "predicted_direction": pred_dir,
            "predictedLabel": pred_dir,
            "true_direction": true_dir,
            "trueLabel": true_dir,
            "is_correct": is_correct,
            "decision_score": round(prob_right, 6),
            "score": round(prob_right, 6),
            "probability_right": round(prob_right, 6),
            "probability_left": round(1.0 - prob_right, 6),
            "raw_logit": round(raw_logit, 6),
            "calibrated_logit": round(calibrated_logit, 6),
            "latency_ms": round(latency_ms, 4),
            "quality": {
                "is_clean": is_clean,
                "status": "PASS" if is_clean else "ARTIFACT_GATED",
                "gate_name": "ArtGate90",
                "eog_ptp_uv": round(float(eog_ptp_uv), 2),
                "threshold_uv": round(float(self.model.thr_90_uv), 2),
            },
            "tta_state": {
                "accumulated_trials": int(self.step_idx),
                "running_logit_bias": round(float(running_bias), 6),
                "cov_condition_log10": round(float(cond_log10), 4),
                "band": self.model.band_name,
                "window": self.model.win_name,
                "reg": self.model.reg,
            },
        }
        self.history.append(record)
        return record


# ---------------------------------------------------------------------------
# Offline Protocol Primitives (Exact match to run_8core_turbo_boost.py)
# ---------------------------------------------------------------------------
def fast_welch_fft_psd(X: np.ndarray, f_lo: float, f_hi: float) -> np.ndarray:
    """Vectorized Hann-windowed Welch PSD via rfft from run_8core_turbo_boost.py."""
    N, C, T = X.shape
    seg = min(125, T)
    step = max(1, seg // 2)
    starts = list(range(0, T - seg + 1, step))
    if not starts:
        starts = [0]
    win = np.hanning(seg)[None, None, :]
    freqs = np.fft.rfftfreq(512, d=1.0 / FS)
    msk = (freqs >= f_lo) & (freqs <= f_hi)
    acc = np.zeros((N, C), dtype=np.float64)
    for s0 in starts:
        chunk = X[:, :, s0 : s0 + seg]
        chunk = (chunk - np.mean(chunk, axis=-1, keepdims=True)) * win
        spec = np.abs(np.fft.rfft(chunk, n=512, axis=-1)[..., msk]) ** 2
        acc += np.mean(spec, axis=-1)
    return np.log10(np.maximum(acc / len(starts), 1e-30))


def inband_logpower(X: np.ndarray) -> np.ndarray:
    Xc = X - np.mean(X, axis=-1, keepdims=True)
    return np.log10(np.maximum(np.mean(Xc ** 2, axis=-1), 1e-30))


def extract_erd_asym(lp_mi: np.ndarray, lp_fix: np.ndarray, ch_idx: list[int]) -> np.ndarray:
    erd = 10.0 * (lp_mi - lp_fix)
    feats = [lp_mi, erd]
    pos_map = {orig_c: k for k, orig_c in enumerate(ch_idx)}
    asym = []
    for l_c, r_c in HOMOLOGOUS_16:
        if l_c in pos_map and r_c in pos_map:
            li, ri = pos_map[l_c], pos_map[r_c]
            asym.append((10.0 * (lp_mi[:, ri] - lp_mi[:, li]))[:, None])
            asym.append((erd[:, ri] - erd[:, li])[:, None])
    if asym:
        feats.append(np.hstack(asym))
    return np.hstack(feats)


def oas_cov_and_log(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """OAS shrinkage covariance + Ensure-SPD floor (1e-5) + matrix log from run_8core_turbo_boost.py."""
    N, C, T = X.shape
    X_c = X - np.mean(X, axis=2, keepdims=True)
    S = (X_c @ np.swapaxes(X_c, 1, 2)) / float(T)
    tr_S = np.trace(S, axis1=1, axis2=2)
    tr_S2 = np.sum(S * S, axis=(1, 2))
    mu = np.maximum(tr_S / float(C), 1e-24)
    num = (1.0 - 2.0 / C) * tr_S2 + (tr_S ** 2)
    den = (T + 1.0 - 2.0 / C) * (tr_S2 - (tr_S ** 2) / C)
    alpha = np.where(den > 1e-30, np.clip(num / np.maximum(den, 1e-30), 0.0, 1.0), 1.0)
    eye_c = np.eye(C, dtype=np.float64)[None, :, :]
    C_reg = (1.0 - alpha[:, None, None]) * (S / mu[:, None, None]) + alpha[:, None, None] * eye_c
    C_reg = 0.5 * (C_reg + np.swapaxes(C_reg, 1, 2))
    vals, vecs = np.linalg.eigh(C_reg)
    vals = np.maximum(vals, 1e-5)
    covs = (vecs * vals[:, None, :]) @ np.swapaxes(vecs, 1, 2)
    log_covs = (vecs * np.log(vals)[:, None, :]) @ np.swapaxes(vecs, 1, 2)
    return covs, log_covs, S


def fit_log_euclid_ts_ref(log_covs_tr: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[np.ndarray, np.ndarray]]:
    """Fits Log-Euclidean reference whitening matrix `inv_sqrt_m` on training log-covariances."""
    C = log_covs_tr.shape[1]
    mean_log = np.mean(log_covs_tr, axis=0)
    m_vals, m_vecs = np.linalg.eigh(0.5 * (mean_log + mean_log.T))
    inv_sqrt_m = (m_vecs * np.exp(-0.5 * m_vals)) @ m_vecs.T
    iu = np.triu_indices(C)
    weights = np.ones((C, C), dtype=np.float64) * np.sqrt(2.0)
    np.fill_diagonal(weights, 1.0)
    w_vec = weights[iu]
    return inv_sqrt_m, w_vec, iu


def transform_log_euclid_ts(
    covs: np.ndarray,
    inv_sqrt_m: np.ndarray,
    w_vec: np.ndarray,
    iu: tuple[np.ndarray, np.ndarray],
) -> np.ndarray:
    w_cov = inv_sqrt_m @ covs @ inv_sqrt_m
    w_cov = 0.5 * (w_cov + np.swapaxes(w_cov, 1, 2))
    v, u = np.linalg.eigh(w_cov)
    lc = (u * np.log(np.maximum(v, 1e-8))[:, None, :]) @ np.swapaxes(u, 1, 2)
    return lc[:, iu[0], iu[1]] * w_vec[None, :]


def fit_offline_csp(scms_tr: np.ndarray, y_tr: np.ndarray, n_comp: int = 4, reg: float = 0.05) -> np.ndarray:
    C = scms_tr.shape[1]
    s0 = np.mean(scms_tr[y_tr == 0], axis=0)
    s1 = np.mean(scms_tr[y_tr == 1], axis=0)
    eye_c = np.eye(C, dtype=np.float64)
    c0 = (1.0 - reg) * s0 + (reg + 1e-7) * (np.trace(s0) / C) * eye_c
    c1 = (1.0 - reg) * s1 + (reg + 1e-7) * (np.trace(s1) / C) * eye_c
    vals, vecs = eigh(0.5 * (c0 + c0.T), 0.5 * ((c0 + c1) + (c0 + c1).T))
    W = vecs[:, np.argsort(np.abs(vals - 0.5))[::-1][:n_comp]]
    return W.T  # (n_comp, C)


@dataclass
class OfflineBranchSubWindowState:
    band_key: str
    f_lo: float
    f_hi: float
    win_sec: tuple[float, float]
    inv_sqrt_m: np.ndarray
    w_vec: np.ndarray
    iu: tuple[np.ndarray, np.ndarray]
    W_csp: np.ndarray


@dataclass
class OfflineSubjectFittedModel:
    """
    Serializable fitted state of an Offline Per-Subject Champion Model
    (WMJ: CSP_WelchPSD_sLDA / SuperHybrid, KGE: Riemann_TS_sLDA, OYJ: SuperHybrid_TS_CSP_ERD, KHY: SuperHybrid / Riemann_TS_LR).
    """
    subject: str
    channel_mode_key: str  # "16ch", "7ch", "5ch", "low"
    montage_name: str
    ch_idx: list[int]
    active_channels: list[str]
    ref_mode: str
    band_mode_name: str
    band_keys: list[str]
    win_name: str
    win_list: list[tuple[float, float]]
    model_arch: str  # "CSP_WelchPSD_sLDA", "Riemann_TS_LR", "Riemann_TS_sLDA", "SuperHybrid_TS_CSP_ERD"
    causal_ea: bool
    logit_cal: str
    subwindows: list[OfflineBranchSubWindowState]
    scaler_main: Any
    clf_main: Any
    scaler_branch2: Any | None = None
    clf_branch2: Any | None = None
    thr_90_uv: float = 100.0
    cv_metrics: dict[str, dict[str, float]] = field(default_factory=dict)


def apply_offline_montage_single(x16: np.ndarray, ch_idx: list[int], ref_mode: str) -> np.ndarray:
    """Applies global_car, local_car, or none to a single trial `(16, T)` or `(C, T)`."""
    if x16.shape[0] == 16:
        if ref_mode == "global_car":
            return (x16 - np.mean(x16, axis=0, keepdims=True))[ch_idx, :]
        sub = x16[ch_idx, :].copy()
    elif x16.shape[0] == len(ch_idx):
        sub = x16.copy()
    else:
        raise ValueError(f"Expected 16 or {len(ch_idx)} channels, got {x16.shape[0]}")
    if ref_mode == "local_car":
        return sub - np.mean(sub, axis=0, keepdims=True)
    return sub


class StatefulOfflineSubjectSession:
    """
    Stateful chronological inference engine for an Offline Subject Champion Model
    (`WMJ`, `KGE`, `OYJ`, `KHY`), supporting causal run-level Euclidean Alignment
    (`prior_weight=1.5, shrink=0.06`) and Causal Logit Centering (`prior_n=2.0`).
    """

    def __init__(self, model: OfflineSubjectFittedModel, tta_override: bool | None = None):
        self.model = model
        self.tta_enabled: bool = model.causal_ea if tta_override is None else bool(tta_override)
        self.reset()

    def reset(self) -> None:
        C = len(self.model.ch_idx)
        n_sub = len(self.model.subwindows)
        self.prior_weight: float = 1.5
        self.shrink: float = 0.06
        self.prior_n: float = 2.0
        self.run_sums: list[np.ndarray] = [
            self.prior_weight * np.eye(C, dtype=np.float64) for _ in range(n_sub)
        ]
        self.counts: list[float] = [self.prior_weight for _ in range(n_sub)]
        self.running_logit_sum: float = 0.0
        self.step_idx: int = 0
        self.history: list[dict[str, Any]] = []

    def step(
        self,
        x_raw_or_bands: np.ndarray | dict[str, np.ndarray],
        eog_ptp_uv: float | None = None,
        true_label_int: int | None = None,
        trial_id: int | None = None,
        timestamp_s: float | None = None,
        n_pre_samples: int = 0,
    ) -> dict[str, Any]:
        t_start = time.perf_counter()
        C = len(self.model.ch_idx)
        eye_c = np.eye(C, dtype=np.float64)

        # Prepare band-filtered streams if raw (16, T) or (C, T) is passed
        if isinstance(x_raw_or_bands, dict):
            band_dict = x_raw_or_bands
            if eog_ptp_uv is None:
                first_arr = next(iter(band_dict.values()))
                eog_ptp_uv = float(np.max(np.ptp(first_arr, axis=-1)))
        else:
            x_in = np.asarray(x_raw_or_bands, dtype=np.float64)
            if x_in.shape[0] > x_in.shape[1] and x_in.shape[1] in (16, C):
                x_in = x_in.T
            notched = sosfilt(SOS_NOTCH, x_in, axis=1)
            if eog_ptp_uv is None:
                if notched.shape[0] == 16:
                    s_end = min(notched.shape[1], n_pre_samples + int(2.0 * FS))
                    eog_ptp_uv = float(np.max(np.ptp(notched[IDX_EOG, n_pre_samples:s_end], axis=1)))
                else:
                    eog_ptp_uv = float(np.max(np.ptp(notched, axis=1)))
            band_dict = {}
            for bk in self.model.band_keys:
                _, _, sos_b = OFFLINE_BAND_DEFS[bk]
                band_dict[bk] = sosfilt(sos_b, notched, axis=1)

        ts_feats: list[np.ndarray] = []
        csp_psd_feats: list[np.ndarray] = []
        csp_psd_erd_feats: list[np.ndarray] = []
        last_cov: np.ndarray | None = None

        for sw_i, sw in enumerate(self.model.subwindows):
            xm = apply_offline_montage_single(band_dict[sw.band_key], self.model.ch_idx, self.model.ref_mode)
            T_tot = xm.shape[1]
            # Fixation baseline logpower (if pre-cue samples exist, else use first 125 samples)
            if n_pre_samples >= int(1.5 * FS):
                lp_fix = inband_logpower(xm[None, :, 0 : int(1.5 * FS)])
            else:
                lp_fix = inband_logpower(xm[None, :, 0 : min(125, T_tot)])

            i0 = n_pre_samples + int(round(sw.win_sec[0] * FS))
            i1 = n_pre_samples + int(round(sw.win_sec[1] * FS))
            if i1 > T_tot:
                i0 = max(0, min(i0, T_tot - 125))
                i1 = T_tot
            xw_raw = xm[:, i0:i1]
            lp_raw = inband_logpower(xw_raw[None, :, :])

            if self.tta_enabled:
                T_w = xw_raw.shape[1]
                scm = (xw_raw @ xw_raw.T) / float(max(T_w, 1))
                tr_n = max(float(np.trace(scm)) / float(C), 1e-24)
                self.run_sums[sw_i] = self.run_sums[sw_i] + (1.0 - self.shrink) * (scm / tr_n) + self.shrink * eye_c
                self.counts[sw_i] += 1.0
                vals, vecs = np.linalg.eigh(self.run_sums[sw_i] / self.counts[sw_i])
                inv_sqrt = (vecs * (1.0 / np.sqrt(np.maximum(vals, 1e-6)))) @ vecs.T
                xw = inv_sqrt @ (xw_raw / np.sqrt(tr_n))
            else:
                xw = xw_raw

            xw_c = (xw - np.mean(xw, axis=-1, keepdims=True))[None, :, :]
            covs, _, _ = oas_cov_and_log(xw_c)
            last_cov = covs[0]

            ts_f = transform_log_euclid_ts(covs, sw.inv_sqrt_m, sw.w_vec, sw.iu)
            ts_feats.append(ts_f)

            p_csp = np.log(np.maximum(np.mean((sw.W_csp @ xw_c[0]) ** 2, axis=-1), 1e-30))[None, :]
            wpsd = fast_welch_fft_psd(xw_c, sw.f_lo, sw.f_hi)
            erd = extract_erd_asym(lp_raw, lp_fix, self.model.ch_idx)
            csp_psd_feats.extend([p_csp, wpsd])
            csp_psd_erd_feats.extend([p_csp, wpsd, erd])

        if self.model.model_arch == "CSP_WelchPSD_sLDA":
            f_vec = np.hstack(csp_psd_feats)
            raw_logit = float(self.model.clf_main.decision_function(self.model.scaler_main.transform(f_vec))[0])
        elif self.model.model_arch in ("Riemann_TS_LR", "Riemann_TS_sLDA"):
            f_vec = np.hstack(ts_feats)
            raw_logit = float(self.model.clf_main.decision_function(self.model.scaler_main.transform(f_vec))[0])
        elif self.model.model_arch == "SuperHybrid_TS_CSP_ERD":
            f_ts = np.hstack(ts_feats)
            f_csp = np.hstack(csp_psd_erd_feats)
            z1 = float(self.model.clf_main.decision_function(self.model.scaler_main.transform(f_ts))[0])
            z2 = float(self.model.clf_branch2.decision_function(self.model.scaler_branch2.transform(f_csp))[0])
            raw_logit = 0.55 * z1 + 0.45 * z2
        else:
            raise ValueError(f"Unsupported offline model_arch: {self.model.model_arch}")

        self.step_idx += 1
        if self.tta_enabled:
            self.running_logit_sum += raw_logit
            running_bias = self.running_logit_sum / (self.prior_n + self.step_idx)
            calibrated_logit = raw_logit - running_bias
        else:
            running_bias = 0.0
            calibrated_logit = raw_logit

        prob_right = float(1.0 / (1.0 + np.exp(-np.clip(calibrated_logit, -30.0, 30.0))))
        pred_int = 1 if prob_right >= 0.5 else 0
        pred_dir = "RIGHT" if pred_int == 1 else "LEFT"
        true_dir = ("RIGHT" if true_label_int == 1 else "LEFT") if true_label_int in (0, 1) else None
        is_correct = (pred_int == true_label_int) if true_label_int in (0, 1) else None
        is_clean = bool((eog_ptp_uv or 0.0) <= self.model.thr_90_uv)
        cond_log10 = compute_cov_condition_log10(last_cov) if last_cov is not None else 0.0
        latency_ms = float((time.perf_counter() - t_start) * 1000.0)

        spec = PARTICIPANT_SPECS.get(self.model.subject, {})
        record = {
            "trial_id": int(trial_id if trial_id is not None else self.step_idx),
            "trialId": int(trial_id if trial_id is not None else self.step_idx),
            "step_index": int(self.step_idx),
            "timestamp": float(timestamp_s if timestamp_s is not None else (self.step_idx - 1) * 2.0),
            "participant_id": self.model.subject,
            "session_id": f"{self.model.subject.lower()}-offline-champion",
            "model_id": spec.get("model_id", f"{self.model.subject.lower()}-offline"),
            "modelId": spec.get("model_id", f"{self.model.subject.lower()}-offline"),
            "model_name": f"{self.model.model_arch} ({self.model.montage_name})",
            "channel_mode": self.model.channel_mode_key,
            "channelSet": self.model.channel_mode_key,
            "montage": self.model.montage_name,
            "n_channels": len(self.model.ch_idx),
            "active_channels": self.model.active_channels,
            "tta_enabled": self.tta_enabled,
            "predicted_direction": pred_dir,
            "predictedLabel": pred_dir,
            "true_direction": true_dir,
            "trueLabel": true_dir,
            "is_correct": is_correct,
            "decision_score": round(prob_right, 6),
            "score": round(prob_right, 6),
            "probability_right": round(prob_right, 6),
            "probability_left": round(1.0 - prob_right, 6),
            "raw_logit": round(raw_logit, 6),
            "calibrated_logit": round(calibrated_logit, 6),
            "latency_ms": round(latency_ms, 4),
            "quality": {
                "is_clean": is_clean,
                "status": "PASS" if is_clean else "ARTIFACT_GATED",
                "gate_name": "ArtGate90",
                "eog_ptp_uv": round(float(eog_ptp_uv or 0.0), 2),
                "threshold_uv": round(float(self.model.thr_90_uv), 2),
            },
            "tta_state": {
                "accumulated_trials": int(self.step_idx),
                "running_logit_bias": round(float(running_bias), 6),
                "cov_condition_log10": round(float(cond_log10), 4),
                "band": self.model.band_mode_name,
                "window": self.model.win_name,
            },
        }
        self.history.append(record)
        return record

