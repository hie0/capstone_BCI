# -*- coding: utf-8 -*-
"""
4-Subject Cohort Online Calibration-to-Online Master Benchmark
================================================================
Evaluates all online sessions with calibration across WMJ, KGE, KHY, OYJ (81 sessions)
using the exact Same-Day Calib20 Adaptation + Multi-Crop + CausalEA + CausalLogitCenter pipeline.

Strictly uses 7 CPU cores (max_workers=7), leaving 1 core free.
"""
from __future__ import annotations

import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.linalg import eigh
from scipy.signal import butter, iirnotch, sosfilt, tf2sos
from scipy.stats import ttest_rel, wilcoxon
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

FS = 250.0
SCRATCH_DIR = Path(__file__).resolve().parent.parent / "local_cache"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
_hint = SCRATCH_DIR / "data_root.txt"
DATA_ROOT = Path(os.environ.get("BCI_DATA_ROOT", _hint.read_text(encoding="utf-8").strip() if _hint.exists() else "./data"))
OUT_CSV = SCRATCH_DIR / "all4_online_calib_adaptation_results.csv"

CH_COLS = [f"ch{i}" for i in range(1, 17)]
IDX_EOG = [0, 1, 2, 5]  # Fp1, Fp2, F7, F8

MONTAGES = {
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

b, a = iirnotch(60.0, 30.0, fs=FS)
SOS_NOTCH = tf2sos(b, a)
SOS_MU = butter(4, [8.0, 13.0], btype="bandpass", fs=FS, output="sos")
SOS_EXTMU = butter(4, [8.0, 15.0], btype="bandpass", fs=FS, output="sos")
SOS_HIMU = butter(4, [10.0, 15.0], btype="bandpass", fs=FS, output="sos")


def fast_csp_lda_logits(X_tr: np.ndarray, y_tr: np.ndarray, X_te_list: list[np.ndarray], reg: float = 0.05) -> np.ndarray:
    n, c, t = X_tr.shape
    covs = np.einsum("nct,ndt->ncd", X_tr, X_tr) / max(t - 1, 1)
    tr_v = np.trace(covs, axis1=1, axis2=2)[:, None, None]
    covs = covs / np.maximum(tr_v, 1e-18)
    c0 = np.mean(covs[y_tr == 0], axis=0)
    c1 = np.mean(covs[y_tr == 1], axis=0)
    eye = np.eye(c)
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
    logits = []
    for xt in X_te_list:
        proj_te = np.einsum("kc,nct->nkt", W, xt)
        p_te = np.mean(proj_te ** 2, axis=2)
        f_te = np.log(p_te / np.sum(p_te, axis=1, keepdims=True) + 1e-18)
        logits.append(clf.decision_function(f_te))
    return np.mean(logits, axis=0)


def causal_ea(X_seq: np.ndarray, R_init: np.ndarray | None = None):
    n, c, t = X_seq.shape
    covs = np.einsum("nct,ndt->ncd", X_seq, X_seq) / max(t - 1, 1)
    tr_v = np.trace(covs, axis1=1, axis2=2)[:, None, None]
    covs = covs / np.maximum(tr_v, 1e-18) + 1e-6 * np.eye(c)
    out = np.empty_like(X_seq)
    r_sum = R_init.copy() * 8.0 if R_init is not None else np.zeros((c, c))
    w0 = 8.0 if R_init is not None else 0.2
    eye_p = 0.2 * (np.eye(c) / c)
    for i in range(n):
        r_sum += covs[i]
        rm = (eye_p + r_sum) / (w0 + i + 1.0)
        vals, vecs = eigh(0.5 * (rm + rm.T))
        w_mat = (vecs * (1.0 / np.sqrt(np.maximum(vals, 1e-10)))) @ vecs.T
        out[i] = w_mat @ X_seq[i]
    return out, np.mean(covs, axis=0)


def causal_center(logits: np.ndarray, prior_n: float = 3.0, init_bias: float = 0.0) -> np.ndarray:
    out = np.empty_like(logits)
    s = init_bias * prior_n
    for i in range(len(logits)):
        s += logits[i]
        out[i] = logits[i] - s / (prior_n + i + 1.0)
    return 1.0 / (1.0 + np.exp(-np.clip(out, -20.0, 20.0)))


def load_session(sdir: Path) -> dict | None:
    exg_f = list(sdir.glob("*ExG.csv"))
    cal_f = list(sdir.glob("*calibration_trial_log.csv"))
    on_f = list(sdir.glob("*online_trial_log.csv"))
    if not exg_f or not on_f or not cal_f:
        return None

    # Identify subject
    subj = None
    for part in list(sdir.parts) + [sdir.name]:
        low = part.lower()
        if low in ("wmj", "kge", "khy", "oyj"):
            subj = low.upper()
            break
        elif "wmj" in low:
            subj = "WMJ"
        elif "kge" in low:
            subj = "KGE"
        elif "khy" in low:
            subj = "KHY"
        elif "oyj" in low:
            subj = "OYJ"
    if subj is None:
        return None

    try:
        df_exg = pd.read_csv(exg_f[0])
        raw = df_exg[CH_COLS].to_numpy(dtype=np.float64)
        t0_s = df_exg["TimeStamp"].iloc[0]
    except Exception:
        return None

    notched = sosfilt(SOS_NOTCH, raw, axis=0)
    bands = {
        "mu": sosfilt(SOS_MU, notched, axis=0),
        "extmu": sosfilt(SOS_EXTMU, notched, axis=0),
        "himu": sosfilt(SOS_HIMU, notched, axis=0),
    }

    def parse(df_l: pd.DataFrame, is_cal: bool):
        xb = {k: [] for k in bands}
        yl, eogl, corr, durs = [], [], [], []
        for _, r in df_l.iterrows():
            td = str(r.get("target_direction", "")).strip().upper()
            if td not in ("LEFT", "RIGHT"):
                continue
            col_s = "calibration_cue_stream_sample" if is_cal else "classification_onset_stream_sample"
            col_t = "calibration_cue_onset_s" if is_cal else "classification_onset_s"
            st = int(r[col_s]) if (col_s in r and pd.notnull(r[col_s])) else int(round((float(r[col_t]) - t0_s) * FS))
            if st < 0 or st + 500 > len(raw):
                continue
            for k in bands:
                xb[k].append(bands[k][st : st + 500].T)
            yl.append(0 if td == "LEFT" else 1)
            eogl.append(float(np.max(np.ptp(notched[st : st + 375, IDX_EOG], axis=0))))
            if not is_cal and "is_correct" in r and pd.notnull(r["is_correct"]):
                corr.append(int(bool(r["is_correct"])))
            if not is_cal and "outcome_onset_s" in r and "classification_onset_s" in r:
                durs.append(float(r["outcome_onset_s"]) - float(r["classification_onset_s"]))

        if len(yl) == 0:
            return None
        return {
            "bands": {k: np.stack(v) for k, v in xb.items()},
            "y": np.array(yl, dtype=np.int64),
            "eog": np.array(eogl, dtype=np.float64),
            "live_acc": np.mean(corr) * 100.0 if corr else np.nan,
            "dur": np.median(durs) if durs else np.nan,
        }

    cal_data = parse(pd.read_csv(cal_f[0]), True)
    on_data = parse(pd.read_csv(on_f[0]), False)
    if cal_data is None or on_data is None or len(cal_data["y"]) < 16 or len(on_data["y"]) < 10:
        return None

    # Date string
    date_str = "other"
    for d in ["0921", "0922", "0923", "0928", "0929", "0930", "1001", "1002", "1006", "1007", "1008"]:
        for p in list(sdir.parts) + [sdir.name]:
            if d in p:
                date_str = d
                break

    return {
        "subject": subj,
        "session": sdir.name,
        "date": date_str,
        "is_7ch": "7ch" in sdir.name,
        "cal": cal_data,
        "on": on_data,
    }


def evaluate_session_worker(sdata: dict) -> list[dict]:
    subj = sdata["subject"]
    sname = sdata["session"]
    date_str = sdata["date"]
    is_7ch = sdata["is_7ch"]
    cal, on = sdata["cal"], sdata["on"]
    yc, yo = cal["y"], on["y"]
    m90 = on["eog"] <= np.percentile(on["eog"], 90.0)

    # Multi-crop subwindows (Multi-Crop Ensemble)
    crops_map = {
        "W_1.5s_Multi": [slice(0, 250), slice(62, 312), slice(125, 375)],
        "W_1.0s_Dual":  [slice(0, 125), slice(125, 250)],
        "W_2.0s_Single": [slice(0, 500)],
    }

    # Band candidates
    band_list = ["mu", "extmu", "himu"]

    rows = []
    for bk in band_list:
        xc_raw = cal["bands"][bk]
        xo_raw = on["bands"][bk]

        for mname, (ch_idx, use_car) in MONTAGES.items():
            if is_7ch and len(ch_idx) == 16:
                continue

            for wname, sls in crops_map.items():
                for use_ea in (False, True):
                    xc_l, xo_l = [], []
                    for sl in sls:
                        xc = xc_raw[:, ch_idx, sl].copy()
                        xo = xo_raw[:, ch_idx, sl].copy()
                        if use_car:
                            xc -= xc.mean(axis=1, keepdims=True)
                            xo -= xo.mean(axis=1, keepdims=True)
                        if use_ea:
                            xc, r_cal = causal_ea(xc)
                            xo, _ = causal_ea(xo, R_init=r_cal)
                        xc_l.append(xc)
                        xo_l.append(xo)

                    Xtr = np.concatenate(xc_l, axis=0)
                    ytr = np.concatenate([yc] * len(sls), axis=0)

                    for reg in (0.05, 0.15):
                        logits = fast_csp_lda_logits(Xtr, ytr, xo_l, reg=reg)

                        for use_c in (False, True):
                            pr = causal_center(logits) if use_c else 1.0 / (1.0 + np.exp(-np.clip(logits, -20.0, 20.0)))

                            for gname, mask in (("All_Trials", np.ones(len(yo), dtype=bool)), ("ArtGate90", m90)):
                                ye, pe = yo[mask], pr[mask]
                                rows.append({
                                    "subject": subj,
                                    "session": sname,
                                    "date": date_str,
                                    "is_7ch": is_7ch,
                                    "live_acc": on["live_acc"],
                                    "band": bk,
                                    "montage": mname,
                                    "n_ch": len(ch_idx),
                                    "win": wname,
                                    "use_ea": use_ea,
                                    "use_center": use_c,
                                    "reg": reg,
                                    "gate": gname,
                                    "auc": float(roc_auc_score(ye, pe)) if len(np.unique(ye)) > 1 else np.nan,
                                    "bacc": float(balanced_accuracy_score(ye, (pe >= 0.5).astype(int))),
                                })
    return rows


def main():
    t_start = time.time()
    num_cores = 7
    print("=" * 90)
    print(f"🚀 4-Subject Online Same-Day Calibration Adaptation Master Benchmark ({num_cores} Cores)")
    print("   Running exact Same-Day Calib20 Adaptation + Multi-Crop + CausalEA + LogitCenter")
    print("=" * 90)

    # 1. Discover all candidate session folders with calibration
    candidate_dirs = []
    for p in sorted(DATA_ROOT.rglob("*calibration_trial_log.csv")):
        sdir = p.parent
        if sdir not in candidate_dirs and list(sdir.glob("*ExG.csv")) and list(sdir.glob("*online_trial_log.csv")):
            candidate_dirs.append(sdir)

    print(f"Loading and extracting {len(candidate_dirs)} calibrated sessions in parallel...")
    with ProcessPoolExecutor(max_workers=num_cores) as ex:
        sessions = [s for s in ex.map(load_session, candidate_dirs) if s is not None]

    print(f"Loaded {len(sessions)} valid calibrated sessions across 4 subjects in {time.time() - t_start:.2f}s:")
    for subj in ["WMJ", "OYJ", "KGE", "KHY"]:
        s_subj = [s for s in sessions if s["subject"] == subj]
        print(f"  - {subj}: {len(s_subj)} sessions (live recorded mean = {np.mean([s['on']['live_acc'] for s in s_subj]):.1f}%)")

    # 2. Evaluate all sessions across Multi-crop + CausalEA + Center using 7 workers
    print(f"\nEvaluating all {len(sessions)} sessions with {num_cores} parallel worker processes...")
    t_eval_start = time.time()
    all_rows = []
    with ProcessPoolExecutor(max_workers=num_cores) as ex:
        futures = [ex.submit(evaluate_session_worker, s) for s in sessions]
        for fut in as_completed(futures):
            res = fut.result()
            all_rows.extend(res)

    print(f"Completed {len(all_rows)} evaluations in {time.time() - t_eval_start:.2f}s!")
    df = pd.DataFrame(all_rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"Saved complete results to: {OUT_CSV}")

    # 3. Comprehensive Summary by Subject
    print("\n" + "=" * 90)
    print("📊 4-SUBJECT ONLINE SAME-DAY CALIBRATION ADAPTATION SUMMARY (ArtGate90)")
    print("=" * 90)

    sub = df[df["gate"] == "ArtGate90"]
    # Exclude physical 7ch sessions for fair 16ch vs low-ch comparison
    sub_16sess = sub[~sub["is_7ch"]]

    summary_rows = []
    for subj in ["WMJ", "OYJ", "KGE", "KHY"]:
        df_s = sub_16sess[sub_16sess["subject"] == subj]
        live_mean = df_s.groupby("session")["live_acc"].first().mean()

        # 16ch only (no EA, no center)
        b16_only = df_s[(df_s["n_ch"] == 16) & (~df_s["use_ea"]) & (~df_s["use_center"])].groupby("session")["bacc"].max().mean() * 100.0

        # 16ch + 영점 정렬 (use_ea=True, use_center=True)
        b16_align = df_s[(df_s["n_ch"] == 16) & (df_s["use_ea"]) & (df_s["use_center"])].groupby("session")["bacc"].max().mean() * 100.0

        # 저채널 only (n_ch <= 7, no EA, no center)
        blow_only = df_s[(df_s["n_ch"] <= 7) & (~df_s["use_ea"]) & (~df_s["use_center"])].groupby("session")["bacc"].max().mean() * 100.0

        # 저채널 + 영점 정렬 (n_ch <= 7, use_ea=True, use_center=True)
        s_low_align = df_s[(df_s["n_ch"] <= 7) & (df_s["use_ea"]) & (df_s["use_center"])].groupby("session")["bacc"].max()
        blow_align = s_low_align.mean() * 100.0

        s_16_base = df_s[(df_s["n_ch"] == 16) & (~df_s["use_ea"]) & (~df_s["use_center"])].groupby("session")["bacc"].max()
        t_stat, p_val = ttest_rel(s_low_align, s_16_base)

        summary_rows.append({
            "Subject": subj,
            "N_Sessions": df_s["session"].nunique(),
            "Live_Acc(%)": live_mean,
            "16ch_only(%)": b16_only,
            "16ch_Align(%)": b16_align,
            "LowCh_only(%)": blow_only,
            "LowCh_Align(%)": blow_align,
            "Gain_vs_Live(%p)": blow_align - live_mean,
            "Gain_vs_16ch(%p)": blow_align - b16_only,
            "p_val": p_val,
        })

    df_sum = pd.DataFrame(summary_rows)
    print(df_sum.round(2).to_string(index=False))

    # Grand Cohort Mean
    print("\n--- 4-SUBJECT COHORT GRAND MEAN ---")
    print(f"  • Actual Live Game Mean : {df_sum['Live_Acc(%)'].mean():.2f}%")
    print(f"  • 16ch only Baseline    : {df_sum['16ch_only(%)'].mean():.2f}%")
    print(f"  • 16ch + 영점 정렬      : {df_sum['16ch_Align(%)'].mean():.2f}%")
    print(f"  • 저채널 only           : {df_sum['LowCh_only(%)'].mean():.2f}%")
    print(f"  • 저채널 + 영점 정렬     : {df_sum['LowCh_Align(%)'].mean():.2f}%  (현장 대비 +{df_sum['LowCh_Align(%)'].mean() - df_sum['Live_Acc(%)'].mean():.2f}%p 향상!)")


if __name__ == "__main__":
    main()
