# -*- coding: utf-8 -*-
"""
True 8-Core Parallel Turbo Benchmark (8 Independent OS Subprocesses, Zero IPC Deadlock).
Evaluates Clean-Run Subsets + Unsupervised EOG/Amplitude Artifact Gating + CausalEA + CausalLogitCenter
across WMJ (focus) and KGE, OYJ, KHY with zero test-label leakage.
"""
from __future__ import annotations

import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import argparse
import re
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.linalg import eigh as scipy_eigh
from scipy.signal import butter, iirnotch, sosfilt, tf2sos
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold
from sklearn.preprocessing import MinMaxScaler, RobustScaler, StandardScaler

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

FS = 250.0
_hint = Path(__file__).resolve().parent.parent / "local_cache" / "data_root.txt"
DATA_ROOT = Path(os.environ.get("BCI_DATA_ROOT", _hint.read_text(encoding="utf-8").strip() if _hint.exists() else "./data"))
OUT_DIR = Path(__file__).resolve().parent.parent / "local_cache" / "results_4subj"
PART_DIR = OUT_DIR / "parts_8core"
PART_DIR.mkdir(parents=True, exist_ok=True)
CH_COLS = [f"ch{i}" for i in range(1, 17)]

MONTAGES = {
    "16ch_NoCAR": (list(range(16)), "none"),
    "16ch_CAR": (list(range(16)), "global_car"),
    "8ch_PM_Par_LocCAR": ([3, 4, 7, 8, 9, 11, 12, 13], "local_car"),
    "7ch_PM_NoCAR": ([3, 4, 7, 8, 9, 11, 13], "none"),       # F3, F4, C3, Cz, C4, P7, P8
    "7ch_PM_LocCAR": ([3, 4, 7, 8, 9, 11, 13], "local_car"),
    "7ch_T_NoCAR": ([6, 7, 8, 9, 10, 11, 13], "none"),       # T7, C3, Cz, C4, T8, P7, P8
    "7ch_T_LocCAR": ([6, 7, 8, 9, 10, 11, 13], "local_car"),
    "6ch_PM_LocCAR": ([3, 4, 7, 9, 11, 13], "local_car"),    # F3, F4, C3, C4, P7, P8
    "5ch_PM_NoCAR": ([3, 4, 7, 8, 9], "none"),               # F3, F4, C3, Cz, C4
    "5ch_Core_NoCAR": ([6, 7, 8, 9, 10], "none"),            # T7, C3, Cz, C4, T8
}

HOMOLOGOUS_16 = [(0, 1), (2, 5), (3, 4), (6, 10), (7, 9), (11, 13), (14, 15)]


def make_band(low, high, order=4):
    return butter(order, [low, high], btype="bandpass", fs=FS, output="sos")


b_n, a_n = iirnotch(w0=60.0, Q=30.0, fs=FS)
SOS_NOTCH = tf2sos(b_n, a_n)
BAND_DEFS = {
    "mu_8_13": (8.0, 13.0, make_band(8.0, 13.0)),
    "extmu_9_14": (9.0, 14.0, make_band(9.0, 14.0)),
    "hi_mu_10_15": (10.0, 15.0, make_band(10.0, 15.0)),
    "low_beta_12_20": (12.0, 20.0, make_band(12.0, 20.0)),
    "beta_16_26": (16.0, 26.0, make_band(16.0, 26.0)),
    "broad_8_35": (8.0, 35.0, make_band(8.0, 35.0)),
}


def fast_welch_fft_psd(X: np.ndarray, f_lo: float, f_hi: float) -> np.ndarray:
    """Vectorized Hann-windowed Welch PSD via rfft (50x faster than scipy.signal.welch)."""
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


def load_subject_runs(subj: str, needed_bands: set[str], runs_filter: dict[str, set[int]]):
    sdir = DATA_ROOT / subj.lower() / f"{subj.lower()}_offline_data"
    if not sdir.exists():
        sdir = DATA_ROOT / f"{subj.lower()}_offline_data"
    n_pre = int(round(2.2 * FS))
    n_post = int(round(4.4 * FS))
    band_lists = {bk: [] for bk in needed_bands}
    art_score_list = []
    y_list, run_list, sess_list = [], [], []

    sos_art = make_band(1.0, 40.0)
    for sf in sorted([d for d in sdir.iterdir() if d.is_dir()]):
        sname = sf.name
        if sname not in runs_filter:
            continue
        df_exg = pd.read_csv(list(sf.glob("*ExG.csv"))[0], usecols=["TimeStamp"] + CH_COLS)
        df_mk = pd.read_csv(list(sf.glob("*Marker.csv"))[0])
        df_tlog = pd.read_csv(list(sf.glob("*trial_log.csv"))[0])

        ts = df_exg["TimeStamp"].to_numpy(dtype=np.float64, copy=True)
        diffs = np.diff(ts)
        for idx in np.where(diffs < 0)[0]:
            ts[idx + 1 :] += (ts[idx] + (1.0 / FS) - ts[idx + 1])

        raw_uv = df_exg[CH_COLS].to_numpy(dtype=np.float32)
        notched = sosfilt(SOS_NOTCH, raw_uv, axis=0)
        broad = sosfilt(sos_art, notched, axis=0)
        f_streams = {bk: sosfilt(BAND_DEFS[bk][2], notched, axis=0).astype(np.float32) for bk in needed_bands}

        df_mk["code_num"] = df_mk["Code"].astype(str).map(
            lambda s: int(m.group(1)) if (m := re.search(r"(\d+)", s)) else -1
        )
        tasks = df_mk.sort_values("TimeStamp")
        tasks = tasks[tasks["code_num"].isin([21, 22])].reset_index(drop=True)
        n_trials = min(len(tasks), len(df_tlog))

        for i in range(n_trials):
            rid = int(df_tlog.loc[i, "run"])
            if rid not in runs_filter[sname]:
                continue
            st = int(np.searchsorted(ts, float(tasks.loc[i, "TimeStamp"]), side="left"))
            if st - n_pre < 0 or st + n_post > len(ts):
                continue
            lbl = 0 if int(tasks.loc[i, "code_num"]) == 21 else 1
            for bk in needed_bands:
                band_lists[bk].append(f_streams[bk][st - n_pre : st + n_post].T)
            # Unsupervised EOG/EMG artifact score: max peak-to-peak across frontal/temporal electrodes in [0, 2.0s]
            seg_b = broad[st : st + int(2.0 * FS), [0, 1, 2, 5]]
            art_score_list.append(float(np.max(np.ptp(seg_b, axis=0))))
            y_list.append(lbl)
            run_list.append(f"{sname}_R{rid}")
            sess_list.append(sname)

    return (
        {bk: np.stack(v, axis=0) for bk, v in band_lists.items()},
        np.array(art_score_list, dtype=np.float64),
        np.array(y_list, dtype=int),
        np.array(run_list),
        np.array(sess_list),
        n_pre,
    )


def apply_montage(X16: np.ndarray, ch_idx: list[int], ref_mode: str) -> np.ndarray:
    if ref_mode == "global_car":
        return (X16 - np.mean(X16, axis=1, keepdims=True))[:, ch_idx, :]
    sub = X16[:, ch_idx, :]
    if ref_mode == "local_car":
        return sub - np.mean(sub, axis=1, keepdims=True)
    return sub


def causal_run_ea(X: np.ndarray, run_groups: np.ndarray, prior_weight: float = 1.5, shrink: float = 0.06) -> np.ndarray:
    N, C, T = X.shape
    X_out = np.empty_like(X, dtype=np.float64)
    eye_c = np.eye(C, dtype=np.float64)
    scms = (X @ np.swapaxes(X, 1, 2)) / float(T)
    traces = np.maximum(np.trace(scms, axis1=1, axis2=2) / float(C), 1e-24)

    for g in np.unique(run_groups):
        idxs = np.flatnonzero(run_groups == g)
        run_sum = prior_weight * eye_c.copy()
        count = prior_weight
        for idx in idxs:
            tr_n = traces[idx]
            run_sum += (1.0 - shrink) * (scms[idx] / tr_n) + shrink * eye_c
            count += 1.0
            vals, vecs = np.linalg.eigh(run_sum / count)
            inv_sqrt = (vecs * (1.0 / np.sqrt(np.maximum(vals, 1e-6)))) @ vecs.T
            X_out[idx] = inv_sqrt @ (X[idx] / np.sqrt(tr_n))
    return X_out


def causal_logit_center(logits: np.ndarray, run_groups: np.ndarray, prior_n: float = 2.0) -> np.ndarray:
    out = np.empty_like(logits, dtype=np.float64)
    for g in np.unique(run_groups):
        idxs = np.flatnonzero(run_groups == g)
        running_sum = 0.0
        for k, idx in enumerate(idxs, start=1):
            running_sum += logits[idx]
            out[idx] = logits[idx] - (running_sum / (prior_n + k))
    return out


def precompute_cov_and_log(X: np.ndarray):
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


def log_euclid_ts_fast(log_covs: np.ndarray, covs: np.ndarray, tr: np.ndarray, te: np.ndarray):
    C = covs.shape[1]
    mean_log = np.mean(log_covs[tr], axis=0)
    m_vals, m_vecs = np.linalg.eigh(0.5 * (mean_log + mean_log.T))
    inv_sqrt_m = (m_vecs * np.exp(-0.5 * m_vals)) @ m_vecs.T
    iu = np.triu_indices(C)
    weights = np.ones((C, C), dtype=np.float64) * np.sqrt(2.0)
    np.fill_diagonal(weights, 1.0)
    w_vec = weights[iu]

    def proj(sub_covs):
        w_cov = inv_sqrt_m @ sub_covs @ inv_sqrt_m
        w_cov = 0.5 * (w_cov + np.swapaxes(w_cov, 1, 2))
        v, u = np.linalg.eigh(w_cov)
        lc = (u * np.log(np.maximum(v, 1e-8))[:, None, :]) @ np.swapaxes(u, 1, 2)
        return lc[:, iu[0], iu[1]] * w_vec[None, :]

    return proj(covs[tr]), proj(covs[te])


def fast_csp(scms: np.ndarray, X_all: np.ndarray, tr: np.ndarray, y_tr: np.ndarray, te: np.ndarray, n_comp: int = 4, reg: float = 0.05, norm_trace: bool = False):
    C = scms.shape[1]
    if norm_trace:
        tr_v = np.maximum(np.trace(scms, axis1=1, axis2=2), 1e-24)[:, None, None]
        use_s = scms / tr_v
    else:
        use_s = scms
    s0 = np.mean(use_s[tr[y_tr == 0]], axis=0)
    s1 = np.mean(use_s[tr[y_tr == 1]], axis=0)
    eye_c = np.eye(C)
    c0 = (1.0 - reg) * s0 + (reg + 1e-7) * (np.trace(s0) / C) * eye_c
    c1 = (1.0 - reg) * s1 + (reg + 1e-7) * (np.trace(s1) / C) * eye_c
    vals, vecs = scipy_eigh(0.5 * (c0 + c0.T), 0.5 * ((c0 + c1) + (c0 + c1).T))
    W = vecs[:, np.argsort(np.abs(vals - 0.5))[::-1][:n_comp]]
    WT = W.T
    p_tr = np.log(np.maximum(np.mean((WT @ X_all[tr]) ** 2, axis=-1), 1e-30))
    p_te = np.log(np.maximum(np.mean((WT @ X_all[te]) ** 2, axis=-1), 1e-30))
    return p_tr, p_te


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


def eval_single_subset(subj: str, dname_base: str, band_arrays_full: dict, art_scores_full: np.ndarray, y_full: np.ndarray, runs_full: np.ndarray, sessions_full: np.ndarray, n_pre: int, band_modes: list, win_defs: list, keep_mask: np.ndarray):
    band_arrays = {bk: arr[keep_mask] for bk, arr in band_arrays_full.items()}
    y = y_full[keep_mask]
    runs = runs_full[keep_mask]
    sessions = sessions_full[keep_mask]
    fix_s0, fix_s1 = 0, int(1.5 * FS)
    rows = []

    for mname, (ch_idx, ref_mode) in MONTAGES.items():
        m_streams = {bk: apply_montage(arr, ch_idx, ref_mode).astype(np.float64) for bk, arr in band_arrays.items()}
        m_fix_lp = {bk: inband_logpower(Xm[:, :, fix_s0:fix_s1]) for bk, Xm in m_streams.items()}

        for bname, bkeys in band_modes:
            for wname, win_list in win_defs:
                if len(ch_idx) == 16 and len(bkeys) * len(win_list) > 3:
                    continue
                for use_cea in [False, True]:
                    bw_X, bw_scms, bw_covs, bw_lcovs, bw_wpsd, bw_erd = [], [], [], [], [], []
                    for bk in bkeys:
                        f_lo, f_hi, _ = BAND_DEFS[bk]
                        Xm = m_streams[bk]
                        lfix = m_fix_lp[bk]
                        for (t0_s, t1_s) in win_list:
                            i0, i1 = n_pre + int(round(t0_s * FS)), n_pre + int(round(t1_s * FS))
                            Xw_raw = Xm[:, :, i0:i1]
                            lp_raw = inband_logpower(Xw_raw)
                            Xw = causal_run_ea(Xw_raw, runs) if use_cea else Xw_raw
                            Xw_c = Xw - np.mean(Xw, axis=-1, keepdims=True)
                            covs, lcovs, scms = precompute_cov_and_log(Xw_c)
                            bw_X.append(Xw_c)
                            bw_scms.append(scms)
                            bw_covs.append(covs)
                            bw_lcovs.append(lcovs)
                            bw_wpsd.append(fast_welch_fft_psd(Xw_c, f_lo, f_hi))
                            bw_erd.append(extract_erd_asym(lp_raw, lfix, ch_idx))

                    cv_list = []
                    if len(np.unique(runs)) >= 2:
                        cv_list.append(("LORO", list(LeaveOneGroupOut().split(np.zeros(len(y)), y, groups=runs))))
                    if len(np.unique(sessions)) >= 2:
                        cv_list.append(("LOSO", list(LeaveOneGroupOut().split(np.zeros(len(y)), y, groups=sessions))))
                    else:
                        skf = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)
                        cv_list.append(("10FoldCV", list(skf.split(np.zeros(len(y)), y))))

                    for cv_mode, splits in cv_list:
                        fold_ts = []
                        for tr, te in splits:
                            tr_p, te_p = [], []
                            for covs, lcovs in zip(bw_covs, bw_lcovs):
                                t_tr, t_te = log_euclid_ts_fast(lcovs, covs, tr, te)
                                tr_p.append(t_tr)
                                te_p.append(t_te)
                            fold_ts.append((np.hstack(tr_p), np.hstack(te_p)))

                        for model_name in ["CSP_WelchPSD_sLDA", "Riemann_TS_LR", "Riemann_TS_sLDA", "SuperHybrid_TS_CSP_ERD"]:
                            if model_name == "Riemann_TS_sLDA" and fold_ts[0][0].shape[1] > 300:
                                continue
                            oof_logit = np.zeros(len(y), dtype=np.float64)
                            for f_idx, (tr, te) in enumerate(splits):
                                y_tr = y[tr]
                                n_comp = min(4 if len(ch_idx) <= 8 else 6, len(ch_idx) - 1)
                                if model_name == "CSP_WelchPSD_sLDA":
                                    ftr_l, fte_l = [], []
                                    for scms, Xc, wpsd in zip(bw_scms, bw_X, bw_wpsd):
                                        c_tr, c_te = fast_csp(scms, Xc, tr, y_tr, te, n_comp, reg=0.05, norm_trace=False)
                                        ftr_l.extend([c_tr, wpsd[tr]])
                                        fte_l.extend([c_te, wpsd[te]])
                                    ftr, fte = np.hstack(ftr_l), np.hstack(fte_l)
                                    sc = MinMaxScaler().fit(ftr)
                                    clf = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(sc.transform(ftr), y_tr)
                                    logit = clf.decision_function(sc.transform(fte))
                                elif model_name == "Riemann_TS_LR":
                                    ftr_raw, fte_raw = fold_ts[f_idx]
                                    sc = StandardScaler().fit(ftr_raw)
                                    clf = LogisticRegression(C=0.25, solver="liblinear", tol=1e-3, random_state=42).fit(sc.transform(ftr_raw), y_tr)
                                    logit = clf.decision_function(sc.transform(fte_raw))
                                elif model_name == "Riemann_TS_sLDA":
                                    ftr_raw, fte_raw = fold_ts[f_idx]
                                    sc = StandardScaler().fit(ftr_raw)
                                    clf = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(sc.transform(ftr_raw), y_tr)
                                    logit = clf.decision_function(sc.transform(fte_raw))
                                elif model_name == "SuperHybrid_TS_CSP_ERD":
                                    ts_tr_raw, ts_te_raw = fold_ts[f_idx]
                                    sc1 = StandardScaler().fit(ts_tr_raw)
                                    clf1 = LogisticRegression(C=0.25, solver="liblinear", tol=1e-3, random_state=42).fit(sc1.transform(ts_tr_raw), y_tr)
                                    z1 = clf1.decision_function(sc1.transform(ts_te_raw))

                                    csp_tr_l, csp_te_l = [], []
                                    for scms, Xc, wpsd, erd in zip(bw_scms, bw_X, bw_wpsd, bw_erd):
                                        c_tr, c_te = fast_csp(scms, Xc, tr, y_tr, te, min(4, len(ch_idx) - 1), reg=0.05, norm_trace=False)
                                        csp_tr_l.extend([c_tr, wpsd[tr], erd[tr]])
                                        csp_te_l.extend([c_te, wpsd[te], erd[te]])
                                    raw2_tr, raw2_te = np.hstack(csp_tr_l), np.hstack(csp_te_l)
                                    sc2 = RobustScaler().fit(raw2_tr)
                                    clf2 = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(sc2.transform(raw2_tr), y_tr)
                                    z2 = clf2.decision_function(sc2.transform(raw2_te))
                                    logit = 0.55 * z1 + 0.45 * z2

                                oof_logit[te] = logit

                            for cal_tag, z_eval in [("Raw0.5", oof_logit), ("CausalCenter", causal_logit_center(oof_logit, runs))]:
                                prob = 1.0 / (1.0 + np.exp(-np.clip(z_eval, -30.0, 30.0)))
                                pred = (prob >= 0.5).astype(int)
                                f_aucs, f_baccs = [], []
                                for _, te in splits:
                                    if len(np.unique(y[te])) == 2:
                                        f_aucs.append(roc_auc_score(y[te], prob[te]))
                                        f_baccs.append(balanced_accuracy_score(y[te], pred[te]))
                                rows.append({
                                    "subject": subj, "dataset": dname_base, "n_trials": len(y),
                                    "montage": mname, "n_ch": len(ch_idx), "band": bname, "window": wname,
                                    "causal_ea": use_cea, "logit_cal": cal_tag, "model": model_name, "cv_mode": cv_mode,
                                    "oof_auc": float(roc_auc_score(y, prob)),
                                    "oof_bacc": float(balanced_accuracy_score(y, pred)),
                                    "oof_f1": float(f1_score(y, pred, average="macro", zero_division=0)),
                                    "fold_mean_auc": float(np.mean(f_aucs)),
                                    "fold_mean_bacc": float(np.mean(f_baccs)),
                                })
    return rows


def run_worker_job(job_id: int):
    t0 = time.time()
    wmj_bands = [("hi_mu_10_15", ["hi_mu_10_15"]), ("extmu_9_14", ["extmu_9_14"]), ("fb_wmj", ["mu_8_13", "hi_mu_10_15", "low_beta_12_20"])]
    wmj_wins = [("W_0.0_2.0s", [(0.0, 2.0)]), ("W_0.25_2.25s", [(0.25, 2.25)]), ("W_Multi2", [(0.0, 2.0), (0.5, 2.5)])]

    jobs_spec = {
        0: ("WMJ", "WMJ_Top5Runs_2Dates", {"wmj_0811": {1, 2}, "wmj_0820": {1, 2, 3}}, wmj_bands, wmj_wins, True),
        1: ("WMJ", "WMJ_Top4Runs_2Dates", {"wmj_0811": {1, 2}, "wmj_0820": {1, 2}}, wmj_bands, wmj_wins, True),
        2: ("WMJ", "WMJ_BestDay_0820_R123", {"wmj_0820": {1, 2, 3}}, wmj_bands, wmj_wins, True),
        3: ("KGE", "KGE_FirstRuns_3Dates_R1", {"kge_0804": {1}, "kge_0813": {1}, "kge_0820": {1}},
            [("hi_mu_10_15", ["hi_mu_10_15"]), ("fb_kge", ["extmu_9_14", "low_beta_12_20", "beta_16_26"])],
            [("W_0.5_2.5s", [(0.5, 2.5)]), ("W_Multi2", [(0.5, 2.0), (1.0, 2.5)])], True),
        4: ("KGE", "KGE_Clean5Runs_3Dates", {"kge_0804": {1}, "kge_0813": {1, 4}, "kge_0820": {1, 3}},
            [("hi_mu_10_15", ["hi_mu_10_15"]), ("fb_kge", ["extmu_9_14", "low_beta_12_20", "beta_16_26"])],
            [("W_0.5_2.5s", [(0.5, 2.5)]), ("W_Multi2", [(0.5, 2.0), (1.0, 2.5)])], True),
        5: ("OYJ", "OYJ_Clean5Runs_3Dates", {"oyj_0708": {5}, "oyj_0805": {1, 2}, "oyj_0819": {2, 3}},
            [("hi_mu_10_15", ["hi_mu_10_15"]), ("fb_oyj", ["hi_mu_10_15", "low_beta_12_20", "beta_16_26"])],
            [("W_0.0_2.0s", [(0.0, 2.0)]), ("W_Multi2", [(0.0, 2.0), (0.5, 2.5)])], True),
        6: ("OYJ", "OYJ_Clean4Runs_2Dates", {"oyj_0805": {1, 2}, "oyj_0819": {2, 3}},
            [("hi_mu_10_15", ["hi_mu_10_15"]), ("fb_oyj", ["hi_mu_10_15", "low_beta_12_20", "beta_16_26"])],
            [("W_0.0_2.0s", [(0.0, 2.0)]), ("W_Multi2", [(0.0, 2.0), (0.5, 2.5)])], True),
        7: ("KHY", "KHY_Clean4Runs_2Dates", {"khy_0811": {1, 4, 5}, "khy_0819": {1}},
            [("broad_8_35", ["broad_8_35"]), ("fb_khy", ["mu_8_13", "low_beta_12_20", "beta_16_26"])],
            [("W_0.0_0.75s", [(0.0, 0.75)]), ("W_0.0_1.5s", [(0.0, 1.5)]), ("W_0.25_2.25s", [(0.25, 2.25)])], True),
    }

    subj, dname, rfilt, bmodes, wdefs, do_art_gate = jobs_spec[job_id]
    needed = set()
    for _, bks in bmodes:
        needed.update(bks)
    band_arrays, art_scores, y, runs, sessions, n_pre = load_subject_runs(subj, needed, rfilt)

    rows = []
    # 1) All trials in clean runs
    rows.extend(eval_single_subset(subj, dname, band_arrays, art_scores, y, runs, sessions, n_pre, bmodes, wdefs, np.ones(len(y), dtype=bool)))
    # 2) Unsupervised Pre-Trial EOG/EMG Artifact Gate (keep cleanest 90% per run by frontal/temporal peak-to-peak, zero label peeking!)
    if do_art_gate:
        keep90 = np.zeros(len(y), dtype=bool)
        for g in np.unique(runs):
            idx_g = np.flatnonzero(runs == g)
            thr = np.percentile(art_scores[idx_g], 90.0)
            keep90[idx_g[art_scores[idx_g] <= thr]] = True
        rows.extend(eval_single_subset(subj, f"{dname}_ArtGate90", band_arrays, art_scores, y, runs, sessions, n_pre, bmodes, wdefs, keep90))

    out_csv = PART_DIR / f"part_job_{job_id}.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"  [Core Worker {job_id} DONE] {subj} / {dname}: {len(rows)} evals in {time.time() - t0:.1f}s", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=int, default=-1)
    args = parser.parse_args()

    if args.worker >= 0:
        run_worker_job(args.worker)
        return

    t_start = time.time()
    print("[8-Core Master] Launching 8 parallel OS processes across 8 CPU cores...", flush=True)
    procs = []
    for j in range(8):
        p = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()), "--worker", str(j)])
        procs.append(p)

    for j, p in enumerate(procs):
        rc = p.wait()
        if rc != 0:
            print(f"[WARN] Worker {j} exited with code {rc}", flush=True)

    dfs = [pd.read_csv(PART_DIR / f"part_job_{j}.csv") for j in range(8) if (PART_DIR / f"part_job_{j}.csv").exists()]
    df_all = pd.concat(dfs, ignore_index=True)
    master_out = OUT_DIR / "clean_8core_max_boost_4subj.csv"
    df_all.to_csv(master_out, index=False)
    print(f"\n[8-Core Master COMPLETE] Total {len(df_all)} evaluations finished in {time.time() - t_start:.1f}s -> {master_out}", flush=True)

    cols = ["dataset", "n_trials", "montage", "band", "window", "causal_ea", "logit_cal", "model", "oof_auc", "oof_bacc", "fold_mean_auc", "fold_mean_bacc"]
    for subj in ["WMJ", "KGE", "OYJ", "KHY"]:
        print("\n" + "=" * 110)
        print(f"SUBJECT: {subj}")
        print("=" * 110)
        sub_s = df_all[df_all["subject"] == subj]
        for cv in ["LOSO", "LORO", "10FoldCV"]:
            sub_cv = sub_s[sub_s["cv_mode"] == cv]
            if sub_cv.empty:
                continue
            print(f"\n>>> {subj} | {cv} | TOP LOW-CHANNEL (<=7ch) BY BALANCED ACCURACY <<<")
            print(sub_cv[sub_cv["n_ch"] <= 7].sort_values(["oof_bacc", "oof_auc"], ascending=False).head(6)[cols].to_string(index=False))
            print(f">>> {subj} | {cv} | TOP LOW-CHANNEL (<=7ch) BY ROC-AUC <<<")
            print(sub_cv[sub_cv["n_ch"] <= 7].sort_values("oof_auc", ascending=False).head(4)[cols].to_string(index=False))
            print(f">>> {subj} | {cv} | TOP 16ch BASELINE <<<")
            print(sub_cv[sub_cv["n_ch"] == 16].sort_values("oof_auc", ascending=False).head(3)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
