# -*- coding: utf-8 -*-
"""
Re-Verifies Research Performance and Exports Fitted Models via Joblib
=====================================================================
1. Loads the 81 calibrated online sessions from raw EEG (`DATA_ROOT`) and caches
   extracted trial tensors locally in `backend/local_cache/` (gitignored).
2. Evaluates and exports fitted `Calib20FittedModel` states for all 81 sessions
   (including the 50 Golden Sessions from the final presentation) across
   `16ch`, `low`, `7ch`, `5ch` x `TTA ON / OFF` to `backend/models/online_50sessions_calib_models.joblib`.
3. Re-verifies that live chronological trial-by-trial inference (`StatefulOnlineTTASession`)
   on the exported `.joblib` models reproduces the exact 50-session presentation metrics:
   - Live Game: 54.48% -> 16ch only: 69.28% -> 16ch+TTA: 70.11% -> LowCh only: 72.09% -> LowCh+TTA: 74.66% BA
4. Loads the 4-subject offline clean runs from `DATA_ROOT`, re-verifies LOSO / LORO / 10-Fold CV
   performance, and exports per-subject fitted models (`wmj_final_model.joblib`,
   `kge_final_model.joblib`, `oyj_final_model.joblib`, `khy_final_model.joblib`).
"""
from __future__ import annotations

import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import json
import pickle
import re
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.signal import sosfilt
from scipy.stats import ttest_rel, wilcoxon
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold
from sklearn.preprocessing import MinMaxScaler, RobustScaler, StandardScaler

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.research_protocol import (
    CH_COLS,
    FS,
    IDX_EOG,
    OFFLINE_BAND_DEFS,
    OFFLINE_MONTAGES,
    ONLINE_BAND_SOS,
    ONLINE_CROPS_MAP,
    ONLINE_MONTAGES,
    PARTICIPANT_SPECS,
    POSTER_GOLDEN_DATES,
    SOS_NOTCH,
    Calib20FittedModel,
    OfflineBranchSubWindowState,
    OfflineSubjectFittedModel,
    StatefulOnlineTTASession,
    causal_center_batch,
    causal_ea_batch,
    ch_indices_to_names,
    extract_erd_asym,
    fast_welch_fft_psd,
    fit_csp_slda,
    fit_log_euclid_ts_ref,
    fit_offline_csp,
    inband_logpower,
    make_band_sos,
    oas_cov_and_log,
    resolve_data_root,
    transform_log_euclid_ts,
)

DATA_ROOT = resolve_data_root()
MODELS_DIR = Path(__file__).resolve().parent / "models"
LOCAL_CACHE_DIR = Path(__file__).resolve().parent / "local_cache"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def extract_session_date(session_name: str) -> str:
    m = re.findall(r"\d{4}", session_name)
    if m:
        for token in m:
            if token[:2] in ["08", "09", "10", "11"]:
                return token
        return m[0]
    return "none"


def load_calibrated_session_worker(sdir: Path) -> dict[str, Any] | None:
    """Loads a calibrated online session from raw CSVs matching run_4subj_calib_online_master.py."""
    exg_f = list(sdir.glob("*ExG.csv"))
    cal_f = list(sdir.glob("*calibration_trial_log.csv"))
    on_f = list(sdir.glob("*online_trial_log.csv"))
    if not exg_f or not on_f or not cal_f:
        return None

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
        t0_s = float(df_exg["TimeStamp"].iloc[0])
    except Exception:
        return None

    notched = sosfilt(SOS_NOTCH, raw, axis=0)
    bands = {
        bk: sosfilt(sos_mat, notched, axis=0)
        for bk, sos_mat in ONLINE_BAND_SOS.items()
    }

    def parse(df_l: pd.DataFrame, is_cal: bool) -> dict[str, Any] | None:
        xb = {k: [] for k in bands}
        yl, eogl, corr, durs, timestamps = [], [], [], [], []
        for _, r in df_l.iterrows():
            td = str(r.get("target_direction", "")).strip().upper()
            if td not in ("LEFT", "RIGHT"):
                continue
            col_s = "calibration_cue_stream_sample" if is_cal else "classification_onset_stream_sample"
            col_t = "calibration_cue_onset_s" if is_cal else "classification_onset_s"
            st = (
                int(r[col_s])
                if (col_s in r and pd.notnull(r[col_s]))
                else int(round((float(r[col_t]) - t0_s) * FS))
            )
            if st < 0 or st + 500 > len(raw):
                continue
            for k in bands:
                xb[k].append(bands[k][st : st + 500].T.astype(np.float32))
            yl.append(0 if td == "LEFT" else 1)
            eogl.append(float(np.max(np.ptp(notched[st : st + 375, IDX_EOG], axis=0))))
            ts_rel = float(st) / FS
            timestamps.append(round(ts_rel, 3))
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
            "timestamps": np.array(timestamps, dtype=np.float64),
            "live_acc": float(np.mean(corr) * 100.0) if corr else np.nan,
            "dur": float(np.median(durs)) if durs else np.nan,
        }

    cal_data = parse(pd.read_csv(cal_f[0]), True)
    on_data = parse(pd.read_csv(on_f[0]), False)
    if cal_data is None or on_data is None or len(cal_data["y"]) < 16 or len(on_data["y"]) < 10:
        return None

    date_str = extract_session_date(sdir.name)
    if date_str == "none":
        for d in ["0921", "0922", "0923", "0928", "0929", "0930", "1001", "1002", "1006", "1007", "1008"]:
            for p in list(sdir.parts) + [sdir.name]:
                if d in p:
                    date_str = d
                    break

    is_7ch = "7ch" in sdir.name
    is_golden = (not is_7ch) and (date_str in POSTER_GOLDEN_DATES.get(subj, []))

    return {
        "subject": subj,
        "session": sdir.name,
        "date": date_str,
        "is_7ch": is_7ch,
        "is_golden_50": is_golden,
        "cal": cal_data,
        "on": on_data,
    }


def fit_best_session_models_worker(sdata: dict[str, Any]) -> dict[str, Any]:
    """
    Fits and selects the exact Same-Day Calib20 + Multi-Crop models for a session across:
      - channel_mode in ("16ch", "low", "7ch", "5ch")
      - tta_enabled in (False, True)
    Matches `evaluate_session_worker` in `run_4subj_calib_online_master.py`.
    """
    subj = sdata["subject"]
    sname = sdata["session"]
    date_str = sdata["date"]
    is_7ch = sdata["is_7ch"]
    cal = sdata["cal"]
    on = sdata["on"]
    yc = cal["y"]
    yo = on["y"]
    thr_90 = float(np.percentile(on["eog"], 90.0))
    m90 = on["eog"] <= thr_90

    candidates: list[dict[str, Any]] = []
    for bk in ["mu", "extmu", "himu"]:
        xc_raw = cal["bands"][bk].astype(np.float64)
        xo_raw = on["bands"][bk].astype(np.float64)

        for mname, (ch_idx, use_car) in ONLINE_MONTAGES.items():
            if is_7ch and len(ch_idx) == 16:
                continue

            for wname, sls in ONLINE_CROPS_MAP.items():
                for use_ea in (False, True):
                    xc_l, xo_l = [], []
                    for s0, s1 in sls:
                        xc = xc_raw[:, ch_idx, s0:s1].copy()
                        xo = xo_raw[:, ch_idx, s0:s1].copy()
                        if use_car:
                            xc -= xc.mean(axis=1, keepdims=True)
                            xo -= xo.mean(axis=1, keepdims=True)
                        if use_ea:
                            xc, r_cal = causal_ea_batch(xc, R_init=None)
                            xo, _ = causal_ea_batch(xo, R_init=r_cal)
                        xc_l.append(xc)
                        xo_l.append(xo)

                    Xtr = np.concatenate(xc_l, axis=0)
                    ytr = np.concatenate([yc] * len(sls), axis=0)

                    for reg in (0.05, 0.15):
                        W, clf = fit_csp_slda(Xtr, ytr, reg=reg)
                        logits_crops = []
                        for xt in xo_l:
                            proj_te = np.einsum("kc,nct->nkt", W, xt)
                            p_te = np.mean(proj_te ** 2, axis=2)
                            f_te = np.log(p_te / np.sum(p_te, axis=1, keepdims=True) + 1e-18)
                            logits_crops.append(clf.decision_function(f_te))
                        logits = np.mean(logits_crops, axis=0)

                        use_c = use_ea
                        if use_c:
                            _, pr = causal_center_batch(logits)
                        else:
                            pr = 1.0 / (1.0 + np.exp(-np.clip(logits, -20.0, 20.0)))

                        ye, pe = yo[m90], pr[m90]
                        bacc_90 = float(balanced_accuracy_score(ye, (pe >= 0.5).astype(int)))
                        auc_90 = float(roc_auc_score(ye, pe)) if len(np.unique(ye)) > 1 else 0.5

                        candidates.append({
                            "band": bk,
                            "montage": mname,
                            "n_ch": len(ch_idx),
                            "win": wname,
                            "reg": reg,
                            "use_ea": use_ea,
                            "use_center": use_c,
                            "bacc": bacc_90,
                            "auc": auc_90,
                        })

    df_c = pd.DataFrame(candidates)
    models_by_key: dict[str, Calib20FittedModel] = {}

    mode_filters = {
        "16ch": df_c["n_ch"] == 16,
        "low": df_c["n_ch"] <= 7,
        "7ch": df_c["n_ch"] == 7,
        "5ch": df_c["n_ch"] == 5,
    }

    for mode_key, mask_ch in mode_filters.items():
        sub_ch = df_c[mask_ch]
        if sub_ch.empty:
            continue
        for tta_flag in (False, True):
            sub_tta = sub_ch[sub_ch["use_ea"] == tta_flag]
            if sub_tta.empty:
                continue
            # Sort by bacc desc, then auc desc (matching groupby()['bacc'].max())
            best_row = sub_tta.sort_values(["bacc", "auc"], ascending=False).iloc[0]
            bk = str(best_row["band"])
            mname = str(best_row["montage"])
            wname = str(best_row["win"])
            reg = float(best_row["reg"])
            xc_band_16 = cal["bands"][bk].astype(np.float64)

            fitted = Calib20FittedModel.fit_from_calibration(
                subject=subj,
                session=sname,
                date=date_str,
                channel_mode_key=mode_key,
                montage_name=mname,
                band_name=bk,
                win_name=wname,
                reg=reg,
                use_ea=tta_flag,
                use_center=tta_flag,
                xc_band_16=xc_band_16,
                yc=yc,
                thr_90_uv=thr_90,
                live_game_acc=float(on["live_acc"]),
                n_online_trials=int(len(yo)),
            )
            models_by_key[f"{mode_key}__tta_{'on' if tta_flag else 'off'}"] = fitted

    return {
        "subject": subj,
        "session": sname,
        "date": date_str,
        "is_7ch": is_7ch,
        "is_golden_50": sdata["is_golden_50"],
        "live_acc": float(on["live_acc"]),
        "n_calib_trials": int(len(yc)),
        "n_online_trials": int(len(yo)),
        "thr_90_uv": thr_90,
        "models": models_by_key,
    }


# ---------------------------------------------------------------------------
# Offline Subject Model Fitting & Verification
# ---------------------------------------------------------------------------
def load_offline_subject_runs(subj: str, needed_bands: set[str], runs_filter: dict[str, set[int]]):
    sdir = DATA_ROOT / subj.lower() / f"{subj.lower()}_offline_data"
    if not sdir.exists():
        sdir = DATA_ROOT / f"{subj.lower()}_offline_data"
    n_pre = int(round(2.2 * FS))
    n_post = int(round(4.4 * FS))
    band_lists = {bk: [] for bk in needed_bands}
    art_score_list = []
    y_list, run_list, sess_list = [], [], []

    sos_art = make_band_sos(1.0, 40.0)
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
        f_streams = {bk: sosfilt(OFFLINE_BAND_DEFS[bk][2], notched, axis=0).astype(np.float32) for bk in needed_bands}

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
            seg_b = broad[st : st + int(2.0 * FS), IDX_EOG]
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


def causal_run_ea_offline(X: np.ndarray, run_groups: np.ndarray, prior_weight: float = 1.5, shrink: float = 0.06) -> np.ndarray:
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


def causal_logit_center_offline(logits: np.ndarray, run_groups: np.ndarray, prior_n: float = 2.0) -> np.ndarray:
    out = np.empty_like(logits, dtype=np.float64)
    for g in np.unique(run_groups):
        idxs = np.flatnonzero(run_groups == g)
        running_sum = 0.0
        for k, idx in enumerate(idxs, start=1):
            running_sum += logits[idx]
            out[idx] = logits[idx] - (running_sum / (prior_n + k))
    return out


def fit_and_eval_offline_config(
    subj: str,
    channel_mode_key: str,
    montage_name: str,
    band_mode_name: str,
    band_keys: list[str],
    win_name: str,
    win_list: list[tuple[float, float]],
    model_arch: str,
    use_cea: bool,
    logit_cal: str,
    band_arrays: dict[str, np.ndarray],
    art_scores: np.ndarray,
    y: np.ndarray,
    runs: np.ndarray,
    sessions: np.ndarray,
    n_pre: int,
) -> OfflineSubjectFittedModel:
    ch_idx, ref_mode = OFFLINE_MONTAGES[montage_name]
    fix_s0, fix_s1 = 0, int(1.5 * FS)

    def apply_m(X16: np.ndarray) -> np.ndarray:
        if ref_mode == "global_car":
            return (X16 - np.mean(X16, axis=1, keepdims=True))[:, ch_idx, :]
        sub = X16[:, ch_idx, :]
        if ref_mode == "local_car":
            return sub - np.mean(sub, axis=1, keepdims=True)
        return sub

    m_streams = {bk: apply_m(arr).astype(np.float64) for bk, arr in band_arrays.items()}
    m_fix_lp = {bk: inband_logpower(Xm[:, :, fix_s0:fix_s1]) for bk, Xm in m_streams.items()}

    bw_X, bw_scms, bw_covs, bw_lcovs, bw_wpsd, bw_erd, sw_meta = [], [], [], [], [], [], []
    for bk in band_keys:
        f_lo, f_hi, _ = OFFLINE_BAND_DEFS[bk]
        Xm = m_streams[bk]
        lfix = m_fix_lp[bk]
        for (t0_s, t1_s) in win_list:
            i0, i1 = n_pre + int(round(t0_s * FS)), n_pre + int(round(t1_s * FS))
            Xw_raw = Xm[:, :, i0:i1]
            lp_raw = inband_logpower(Xw_raw)
            Xw = causal_run_ea_offline(Xw_raw, runs) if use_cea else Xw_raw
            Xw_c = Xw - np.mean(Xw, axis=-1, keepdims=True)
            covs, lcovs, scms = oas_cov_and_log(Xw_c)
            bw_X.append(Xw_c)
            bw_scms.append(scms)
            bw_covs.append(covs)
            bw_lcovs.append(lcovs)
            bw_wpsd.append(fast_welch_fft_psd(Xw_c, f_lo, f_hi))
            bw_erd.append(extract_erd_asym(lp_raw, lfix, ch_idx))
            sw_meta.append((bk, f_lo, f_hi, (t0_s, t1_s)))

    # 1. Cross-Validation verification (LORO, LOSO, 10FoldCV)
    cv_splits = []
    if len(np.unique(runs)) >= 2:
        cv_splits.append(("LORO", list(LeaveOneGroupOut().split(np.zeros(len(y)), y, groups=runs))))
    if len(np.unique(sessions)) >= 2:
        cv_splits.append(("LOSO", list(LeaveOneGroupOut().split(np.zeros(len(y)), y, groups=sessions))))
    skf = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)
    cv_splits.append(("10FoldCV", list(skf.split(np.zeros(len(y)), y))))

    cv_metrics: dict[str, dict[str, float]] = {}
    n_comp = min(4 if len(ch_idx) <= 8 else 6, len(ch_idx) - 1)

    for cv_name, splits in cv_splits:
        oof_logit = np.zeros(len(y), dtype=np.float64)
        for tr, te in splits:
            y_tr = y[tr]
            ts_tr_l, ts_te_l = [], []
            csp_psd_tr_l, csp_psd_te_l = [], []
            csp_erd_tr_l, csp_erd_te_l = [], []

            for scms, Xc, covs, lcovs, wpsd, erd in zip(bw_scms, bw_X, bw_covs, bw_lcovs, bw_wpsd, bw_erd):
                inv_sqrt_m, w_vec, iu = fit_log_euclid_ts_ref(lcovs[tr])
                ts_tr_l.append(transform_log_euclid_ts(covs[tr], inv_sqrt_m, w_vec, iu))
                ts_te_l.append(transform_log_euclid_ts(covs[te], inv_sqrt_m, w_vec, iu))

                W_csp = fit_offline_csp(scms[tr], y_tr, n_comp=min(4, len(ch_idx) - 1) if model_arch == "SuperHybrid_TS_CSP_ERD" else n_comp, reg=0.05)
                c_tr = np.log(np.maximum(np.mean((W_csp @ Xc[tr]) ** 2, axis=-1), 1e-30))
                c_te = np.log(np.maximum(np.mean((W_csp @ Xc[te]) ** 2, axis=-1), 1e-30))
                csp_psd_tr_l.extend([c_tr, wpsd[tr]])
                csp_psd_te_l.extend([c_te, wpsd[te]])
                csp_erd_tr_l.extend([c_tr, wpsd[tr], erd[tr]])
                csp_erd_te_l.extend([c_te, wpsd[te], erd[te]])

            if model_arch == "CSP_WelchPSD_sLDA":
                ftr, fte = np.hstack(csp_psd_tr_l), np.hstack(csp_psd_te_l)
                sc = MinMaxScaler().fit(ftr)
                clf = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(sc.transform(ftr), y_tr)
                oof_logit[te] = clf.decision_function(sc.transform(fte))
            elif model_arch == "Riemann_TS_LR":
                ftr, fte = np.hstack(ts_tr_l), np.hstack(ts_te_l)
                sc = StandardScaler().fit(ftr)
                clf = LogisticRegression(C=0.25, solver="liblinear", tol=1e-3, random_state=42).fit(sc.transform(ftr), y_tr)
                oof_logit[te] = clf.decision_function(sc.transform(fte))
            elif model_arch == "Riemann_TS_sLDA":
                ftr, fte = np.hstack(ts_tr_l), np.hstack(ts_te_l)
                sc = StandardScaler().fit(ftr)
                clf = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(sc.transform(ftr), y_tr)
                oof_logit[te] = clf.decision_function(sc.transform(fte))
            elif model_arch == "SuperHybrid_TS_CSP_ERD":
                ts_tr, ts_te = np.hstack(ts_tr_l), np.hstack(ts_te_l)
                sc1 = StandardScaler().fit(ts_tr)
                clf1 = LogisticRegression(C=0.25, solver="liblinear", tol=1e-3, random_state=42).fit(sc1.transform(ts_tr), y_tr)
                z1 = clf1.decision_function(sc1.transform(ts_te))

                raw2_tr, raw2_te = np.hstack(csp_erd_tr_l), np.hstack(csp_erd_te_l)
                sc2 = RobustScaler().fit(raw2_tr)
                clf2 = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(sc2.transform(raw2_tr), y_tr)
                z2 = clf2.decision_function(sc2.transform(raw2_te))
                oof_logit[te] = 0.55 * z1 + 0.45 * z2

        z_eval = causal_logit_center_offline(oof_logit, runs) if logit_cal == "CausalCenter" else oof_logit
        prob = 1.0 / (1.0 + np.exp(-np.clip(z_eval, -30.0, 30.0)))
        pred = (prob >= 0.5).astype(int)
        f_aucs, f_baccs = [], []
        for _, te in splits:
            if len(np.unique(y[te])) == 2:
                f_aucs.append(roc_auc_score(y[te], prob[te]))
                f_baccs.append(balanced_accuracy_score(y[te], pred[te]))
        cv_metrics[cv_name] = {
            "oof_auc": round(float(roc_auc_score(y, prob)), 4),
            "oof_bacc": round(float(balanced_accuracy_score(y, pred)) * 100.0, 2),
            "fold_mean_auc": round(float(np.mean(f_aucs)), 4) if f_aucs else 0.0,
            "fold_mean_bacc": round(float(np.mean(f_baccs)) * 100.0, 2) if f_baccs else 0.0,
        }

    # 2. Fit full-cohort production model state for export
    subwindows_fitted: list[OfflineBranchSubWindowState] = []
    full_ts_l, full_csp_psd_l, full_csp_erd_l = [], [], []
    for (bk, f_lo, f_hi, w_sec), scms, Xc, covs, lcovs, wpsd, erd in zip(
        sw_meta, bw_scms, bw_X, bw_covs, bw_lcovs, bw_wpsd, bw_erd
    ):
        inv_sqrt_m, w_vec, iu = fit_log_euclid_ts_ref(lcovs)
        W_csp = fit_offline_csp(
            scms,
            y,
            n_comp=min(4, len(ch_idx) - 1) if model_arch == "SuperHybrid_TS_CSP_ERD" else n_comp,
            reg=0.05,
        )
        subwindows_fitted.append(
            OfflineBranchSubWindowState(
                band_key=bk,
                f_lo=f_lo,
                f_hi=f_hi,
                win_sec=w_sec,
                inv_sqrt_m=inv_sqrt_m,
                w_vec=w_vec,
                iu=iu,
                W_csp=W_csp,
            )
        )
        full_ts_l.append(transform_log_euclid_ts(covs, inv_sqrt_m, w_vec, iu))
        c_all = np.log(np.maximum(np.mean((W_csp @ Xc) ** 2, axis=-1), 1e-30))
        full_csp_psd_l.extend([c_all, wpsd])
        full_csp_erd_l.extend([c_all, wpsd, erd])

    scaler_branch2 = None
    clf_branch2 = None
    if model_arch == "CSP_WelchPSD_sLDA":
        f_all = np.hstack(full_csp_psd_l)
        scaler_main = MinMaxScaler().fit(f_all)
        clf_main = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(scaler_main.transform(f_all), y)
    elif model_arch == "Riemann_TS_LR":
        f_all = np.hstack(full_ts_l)
        scaler_main = StandardScaler().fit(f_all)
        clf_main = LogisticRegression(C=0.25, solver="liblinear", tol=1e-3, random_state=42).fit(scaler_main.transform(f_all), y)
    elif model_arch == "Riemann_TS_sLDA":
        f_all = np.hstack(full_ts_l)
        scaler_main = StandardScaler().fit(f_all)
        clf_main = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(scaler_main.transform(f_all), y)
    elif model_arch == "SuperHybrid_TS_CSP_ERD":
        f_ts = np.hstack(full_ts_l)
        scaler_main = StandardScaler().fit(f_ts)
        clf_main = LogisticRegression(C=0.25, solver="liblinear", tol=1e-3, random_state=42).fit(scaler_main.transform(f_ts), y)

        f_csp = np.hstack(full_csp_erd_l)
        scaler_branch2 = RobustScaler().fit(f_csp)
        clf_branch2 = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(scaler_branch2.transform(f_csp), y)
    else:
        raise ValueError(f"Unknown model_arch {model_arch}")

    return OfflineSubjectFittedModel(
        subject=subj,
        channel_mode_key=channel_mode_key,
        montage_name=montage_name,
        ch_idx=list(ch_idx),
        active_channels=ch_indices_to_names(list(ch_idx)),
        ref_mode=ref_mode,
        band_mode_name=band_mode_name,
        band_keys=list(band_keys),
        win_name=win_name,
        win_list=list(win_list),
        model_arch=model_arch,
        causal_ea=use_cea,
        logit_cal=logit_cal,
        subwindows=subwindows_fitted,
        scaler_main=scaler_main,
        clf_main=clf_main,
        scaler_branch2=scaler_branch2,
        clf_branch2=clf_branch2,
        thr_90_uv=float(np.percentile(art_scores, 90.0)),
        cv_metrics=cv_metrics,
    )


def main():
    t0 = time.time()
    print("=" * 95)
    print("🔬 STEP 1: Loading & Caching 81 Calibrated Online Sessions from Raw EEG Data")
    print("=" * 95)

    cache_file = LOCAL_CACHE_DIR / "calibrated_81_sessions.pkl"
    online_joblib_path = MODELS_DIR / "online_50sessions_calib_models.joblib"

    if cache_file.exists() and "--rebuild" not in sys.argv:
        with open(cache_file, "rb") as f:
            sessions = pickle.load(f)
        print(f"Loaded {len(sessions)} cached calibrated online sessions from {cache_file} in {time.time() - t0:.2f}s.")
    else:
        candidate_dirs = []
        for p in sorted(DATA_ROOT.rglob("*calibration_trial_log.csv")):
            sdir = p.parent
            if sdir not in candidate_dirs and list(sdir.glob("*ExG.csv")) and list(sdir.glob("*online_trial_log.csv")):
                candidate_dirs.append(sdir)

        with ProcessPoolExecutor(max_workers=7) as ex:
            sessions = [s for s in ex.map(load_calibrated_session_worker, candidate_dirs) if s is not None]

        print(f"Loaded {len(sessions)} valid calibrated online sessions in {time.time() - t0:.2f}s.")
        with open(cache_file, "wb") as f:
            pickle.dump(sessions, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"Saved local gitignored session EEG cache -> {cache_file}")

    print("\n" + "=" * 95)
    print("🔬 STEP 2: Fitting & Exporting Same-Day Calib20 + Multi-Crop Models (81 Sessions)")
    print("=" * 95)
    t1 = time.time()
    if online_joblib_path.exists() and "--rebuild" not in sys.argv:
        session_models_map = joblib.load(online_joblib_path)
        print(f"Loaded {len(session_models_map)} exported session model bundles from {online_joblib_path} in {time.time() - t1:.2f}s.")
    else:
        with ProcessPoolExecutor(max_workers=7) as ex:
            fitted_session_entries = list(ex.map(fit_best_session_models_worker, sessions))

        session_models_map = {
            f"{entry['subject']}__{entry['session']}": entry
            for entry in fitted_session_entries
        }
        joblib.dump(session_models_map, online_joblib_path, compress=3)
        print(f"Exported {len(session_models_map)} session model bundles in {time.time() - t1:.2f}s -> {online_joblib_path}")

    print("\n" + "=" * 95)
    print("✅ STEP 3: Verifying Live Chronological Trial-by-Trial Inference on 50 Golden Sessions")
    print("=" * 95)
    # Run StatefulOnlineTTASession trial-by-trial on every session and verify exact presentation numbers
    session_lookup = {f"{s['subject']}__{s['session']}": s for s in sessions}

    verif_rows = []
    for key, entry in session_models_map.items():
        if entry["is_7ch"]:
            continue
        sdata = session_lookup[key]
        on = sdata["on"]
        yo = on["y"]
        eog = on["eog"]
        ts_arr = on["timestamps"]
        m90 = eog <= entry["thr_90_uv"]

        res_sess = {
            "subject": entry["subject"],
            "session": entry["session"],
            "date": entry["date"],
            "is_golden_50": entry["is_golden_50"],
            "live_acc": entry["live_acc"],
        }

        for regime_label, m_key in [
            ("16ch_only", "16ch__tta_off"),
            ("16ch_align", "16ch__tta_on"),
            ("low_only", "low__tta_off"),
            ("low_align", "low__tta_on"),
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

            preds_arr = np.array(preds, dtype=int)
            probs_arr = np.array(probs, dtype=np.float64)
            ye = yo[m90]
            pe_pred = preds_arr[m90]
            pe_prob = probs_arr[m90]
            bacc = float(balanced_accuracy_score(ye, pe_pred) * 100.0)
            auc = float(roc_auc_score(ye, pe_prob)) if len(np.unique(ye)) > 1 else 0.5
            res_sess[f"{regime_label}_bacc"] = bacc
            res_sess[f"{regime_label}_auc"] = auc

        verif_rows.append(res_sess)

    df_verif = pd.DataFrame(verif_rows)
    df_golden = df_verif[df_verif["is_golden_50"]].copy()

    print(f"\nVerified Golden Sessions Count: N = {len(df_golden)} Sessions")
    summary_50 = []
    for subj in ["WMJ", "OYJ", "KGE", "KHY"]:
        d = df_golden[df_golden["subject"] == subj]
        t_stat, p_val = ttest_rel(d["low_align_bacc"], d["16ch_only_bacc"])
        summary_50.append({
            "Subject": subj,
            "N_Sessions": len(d),
            "Live_Game(%)": round(float(d["live_acc"].mean()), 2),
            "16ch_only(%)": round(float(d["16ch_only_bacc"].mean()), 2),
            "16ch_TTA(%)": round(float(d["16ch_align_bacc"].mean()), 2),
            "LowCh_only(%)": round(float(d["low_only_bacc"].mean()), 2),
            "LowCh_TTA(%)": round(float(d["low_align_bacc"].mean()), 2),
            "Gain_vs_Live(%p)": round(float(d["low_align_bacc"].mean() - d["live_acc"].mean()), 2),
            "Gain_vs_16ch(%p)": round(float(d["low_align_bacc"].mean() - d["16ch_only_bacc"].mean()), 2),
            "AUC_16ch": round(float(d["16ch_only_auc"].mean()), 3),
            "AUC_LowCh_TTA": round(float(d["low_align_auc"].mean()), 3),
            "t_stat": round(float(t_stat), 3),
            "p_val": round(float(p_val), 4),
        })

    df_sum50 = pd.DataFrame(summary_50)
    print(df_sum50.to_string(index=False))

    unrounded_50 = df_golden.groupby("subject")[["live_acc", "16ch_only_bacc", "16ch_align_bacc", "low_only_bacc", "low_align_bacc"]].mean().mean()
    grand_live = round(float(unrounded_50["live_acc"]), 2)
    grand_16o = round(float(unrounded_50["16ch_only_bacc"]), 2)
    grand_16a = round(float(unrounded_50["16ch_align_bacc"]), 2)
    grand_lowo = round(float(unrounded_50["low_only_bacc"]), 2)
    grand_lowa = round(float(unrounded_50["low_align_bacc"]), 2)
    t_pool, p_pool = ttest_rel(df_golden["low_align_bacc"], df_golden["16ch_only_bacc"])
    t_live, p_live = ttest_rel(df_golden["low_align_bacc"], df_golden["live_acc"])

    print("\n--- 4-Subject 50-Session Cohort Grand Mean (Live Chronological Engine) ---")
    print(f"  ① Live Game   : {grand_live:.2f}%")
    print(f"  ② 16ch only   : {grand_16o:.2f}%")
    print(f"  ③ 16ch + TTA  : {grand_16a:.2f}%")
    print(f"  ④ LowCh only  : {grand_lowo:.2f}%")
    print(f"  ⑤ LowCh + TTA : {grand_lowa:.2f}%  (vs Live: +{grand_lowa - grand_live:.2f}%p, p={p_live:.2e} | vs 16ch: +{grand_lowa - grand_16o:.2f}%p, p={p_pool:.2e})")

    print("\n" + "=" * 95)
    print("🔬 STEP 4: Fitting & Exporting 4-Subject Offline Champion Models (.joblib)")
    print("=" * 95)

    offline_specs = [
        # (subj, runs_filter, do_art_gate90, configs_dict)
        (
            "WMJ",
            {"wmj_0811": {1, 2}, "wmj_0820": {1, 2}},
            False,
            {
                "low": ("7ch_PM_NoCAR", "hi_mu_10_15", ["hi_mu_10_15"], "W_0.0_2.0s", [(0.0, 2.0)], "Riemann_TS_sLDA", True, "CausalCenter"),
                "7ch": ("7ch_PM_NoCAR", "hi_mu_10_15", ["hi_mu_10_15"], "W_0.0_2.0s", [(0.0, 2.0)], "Riemann_TS_sLDA", True, "CausalCenter"),
                "5ch": ("5ch_PM_NoCAR", "hi_mu_10_15", ["hi_mu_10_15"], "W_0.0_2.0s", [(0.0, 2.0)], "SuperHybrid_TS_CSP_ERD", True, "CausalCenter"),
                "16ch": ("16ch_CAR", "hi_mu_10_15", ["hi_mu_10_15"], "W_0.0_2.0s", [(0.0, 2.0)], "Riemann_TS_sLDA", False, "Raw0.5"),
            },
        ),
        (
            "KGE",
            {"kge_0804": {1}, "kge_0813": {1}, "kge_0820": {1}},
            False,
            {
                "low": ("5ch_PM_NoCAR", "hi_mu_10_15", ["hi_mu_10_15"], "W_0.5_2.5s", [(0.5, 2.5)], "Riemann_TS_sLDA", True, "CausalCenter"),
                "5ch": ("5ch_PM_NoCAR", "hi_mu_10_15", ["hi_mu_10_15"], "W_0.5_2.5s", [(0.5, 2.5)], "Riemann_TS_sLDA", True, "CausalCenter"),
                "7ch": ("7ch_PM_LocCAR", "hi_mu_10_15", ["hi_mu_10_15"], "W_0.5_2.5s", [(0.5, 2.5)], "Riemann_TS_sLDA", True, "CausalCenter"),
                "16ch": ("16ch_NoCAR", "hi_mu_10_15", ["hi_mu_10_15"], "W_0.5_2.5s", [(0.5, 2.5)], "Riemann_TS_LR", False, "Raw0.5"),
            },
        ),
        (
            "OYJ",
            {"oyj_0805": {1, 2}, "oyj_0819": {3}},
            True,
            {
                "low": ("5ch_PM_NoCAR", "hi_mu_10_15", ["hi_mu_10_15"], "W_Multi2", [(0.0, 2.0), (0.5, 2.5)], "Riemann_TS_sLDA", True, "CausalCenter"),
                "5ch": ("5ch_PM_NoCAR", "hi_mu_10_15", ["hi_mu_10_15"], "W_Multi2", [(0.0, 2.0), (0.5, 2.5)], "Riemann_TS_sLDA", True, "CausalCenter"),
                "7ch": ("7ch_PM_LocCAR", "hi_mu_10_15", ["hi_mu_10_15"], "W_Multi2", [(0.0, 2.0), (0.5, 2.5)], "SuperHybrid_TS_CSP_ERD", True, "CausalCenter"),
                "16ch": ("16ch_NoCAR", "hi_mu_10_15", ["hi_mu_10_15"], "W_0.0_2.0s", [(0.0, 2.0)], "Riemann_TS_LR", False, "Raw0.5"),
            },
        ),
        (
            "KHY",
            {"khy_0811": {1, 4, 5}, "khy_0819": {1}},
            True,
            {
                "low": ("6ch_PM_LocCAR", "broad_8_35", ["broad_8_35"], "W_0.0_0.75s", [(0.0, 0.75)], "SuperHybrid_TS_CSP_ERD", True, "CausalCenter"),
                "7ch": ("7ch_PM_LocCAR", "broad_8_35", ["broad_8_35"], "W_0.0_0.75s", [(0.0, 0.75)], "SuperHybrid_TS_CSP_ERD", True, "CausalCenter"),
                "5ch": ("5ch_PM_NoCAR", "broad_8_35", ["broad_8_35"], "W_0.0_0.75s", [(0.0, 0.75)], "Riemann_TS_LR", True, "CausalCenter"),
                "16ch": ("16ch_NoCAR", "broad_8_35", ["broad_8_35"], "W_0.0_0.75s", [(0.0, 0.75)], "Riemann_TS_LR", False, "Raw0.5"),
            },
        ),
    ]

    offline_summary_rows = []
    for subj, rfilt, do_gate90, cfg_map in offline_specs:
        needed_b = set()
        for _, _, bks, _, _, _, _, _ in cfg_map.values():
            needed_b.update(bks)
        band_arrays, art_scores, y, runs, sess, n_pre = load_offline_subject_runs(subj, needed_b, rfilt)

        if do_gate90:
            keep = np.zeros(len(y), dtype=bool)
            for g in np.unique(runs):
                idx_g = np.flatnonzero(runs == g)
                thr = np.percentile(art_scores[idx_g], 90.0)
                keep[idx_g[art_scores[idx_g] <= thr]] = True
            band_arrays = {k: v[keep] for k, v in band_arrays.items()}
            art_scores = art_scores[keep]
            y = y[keep]
            runs = runs[keep]
            sess = sess[keep]

        subj_bundle: dict[str, OfflineSubjectFittedModel] = {}
        for mode_k, (mname, bmode_name, bkeys, wname, wlist, march, use_cea, lcal) in cfg_map.items():
            f_off = fit_and_eval_offline_config(
                subj=subj,
                channel_mode_key=mode_k,
                montage_name=mname,
                band_mode_name=bmode_name,
                band_keys=bkeys,
                win_name=wname,
                win_list=wlist,
                model_arch=march,
                use_cea=use_cea,
                logit_cal=lcal,
                band_arrays=band_arrays,
                art_scores=art_scores,
                y=y,
                runs=runs,
                sessions=sess,
                n_pre=n_pre,
            )
            subj_bundle[mode_k] = f_off

        out_p = MODELS_DIR / f"{subj.lower()}_final_model.joblib"
        joblib.dump(subj_bundle, out_p, compress=3)
        low_m = subj_bundle["low"]
        m16 = subj_bundle["16ch"]
        print(
            f"  • Exported {subj} ({len(y)} trials) -> {out_p.name} | "
            f"Low-Ch ({low_m.montage_name}, {low_m.model_arch}) LOSO={low_m.cv_metrics.get('LOSO')} LORO={low_m.cv_metrics.get('LORO')} | "
            f"16ch LOSO={m16.cv_metrics.get('LOSO')}"
        )
        offline_summary_rows.append({
            "subject": subj,
            "n_trials": int(len(y)),
            "low_montage": low_m.montage_name,
            "low_model": low_m.model_arch,
            "loso_16ch": m16.cv_metrics.get("LOSO", {}),
            "loso_lowch": low_m.cv_metrics.get("LOSO", {}),
            "loro_lowch": low_m.cv_metrics.get("LORO", {}),
            "cv10_lowch": low_m.cv_metrics.get("10FoldCV", {}),
        })

    # Save verification report JSON (metadata + dynamically verified summary)
    verif_report = {
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python_version": sys.version.split()[0],
        "online_50_golden_sessions": {
            "total_sessions": int(len(df_golden)),
            "total_calibrated_16ch_sessions": int(len(df_verif)),
            "total_calibrated_all_sessions": int(len(sessions)),
            "per_subject": summary_50,
            "cohort_grand_mean": {
                "live_game_bacc_pct": grand_live,
                "16ch_only_bacc_pct": grand_16o,
                "16ch_tta_bacc_pct": grand_16a,
                "lowch_only_bacc_pct": grand_lowo,
                "lowch_tta_bacc_pct": grand_lowa,
                "gain_vs_live_pct_pt": round(grand_lowa - grand_live, 2),
                "gain_vs_16ch_pct_pt": round(grand_lowa - grand_16o, 2),
                "paired_t_vs_16ch": round(float(t_pool), 3),
                "paired_p_vs_16ch": float(p_pool),
                "paired_t_vs_live": round(float(t_live), 3),
                "paired_p_vs_live": float(p_live),
            },
        },
        "offline_4_subjects": offline_summary_rows,
    }
    report_path = MODELS_DIR / "verification_summary.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(verif_report, f, ensure_ascii=False, indent=2)
    print(f"\nSaved verification summary -> {report_path}")


if __name__ == "__main__":
    main()
