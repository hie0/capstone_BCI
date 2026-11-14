# -*- coding: utf-8 -*-
"""
NEUROLINK Real-Time EEG Inference FastAPI & WebSocket Server (`backend/app.py`)
===============================================================================
Provides REST and WebSocket endpoints that connect the exported `.joblib` research models
and exact Same-Day Calib20 + Multi-Crop + CausalEA + CausalLogitCenter + ArtGate90
protocols to the NEUROLINK website.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.inference_engine import MODELS_DIR, DATA_ROOT, inference_manager
from backend.research_protocol import ELECTRODE_NAMES_16, PARTICIPANT_SPECS
from backend.schemas import (
    CalibrateSessionRequest,
    ChannelModeLiteral,
    ParticipantIdLiteral,
    SessionConfigRequest,
    SessionEvaluationResponse,
    SingleTrialPredictRequest,
    TrialPredictionResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    inference_manager.load_all()
    yield


app = FastAPI(
    title="NEUROLINK MI-BCI Research Inference Backend",
    description=(
        "Real-time & chronological Motor Imagery EEG inference backend using the fitted models "
        "(Reg-CSP+sLDA, OAS+Riemann TS, SuperHybrid TS+CSP+ERD, Ensure-SPD+TS) and "
        "Same-Day Calib20 + Multi-Crop + CausalEA + CausalLogitCenter + ArtGate90 protocols."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
@app.get("/api/health")
def health_check() -> dict[str, Any]:
    inference_manager.load_all()
    joblib_files = sorted([p.name for p in MODELS_DIR.glob("*.joblib")])
    n_golden = sum(len(v) for v in inference_manager.golden_sessions_by_subject.values())
    return {
        "status": "ok",
        "service": "neurolink-research-backend",
        "models_loaded": inference_manager.loaded,
        "exported_joblib_files": joblib_files,
        "participants": list(PARTICIPANT_SPECS.keys()),
        "calibrated_online_sessions_count": len(inference_manager.online_models_map),
        "golden_50_sessions_count": n_golden,
        "local_eeg_sessions_cached": len(inference_manager.raw_sessions_map),
        "local_eeg_online_trials": sum(len(s['on']['y']) for s in inference_manager.raw_sessions_map.values()),
        "data_root": str(DATA_ROOT),
        "runtime_backend": str(Path(__file__).resolve().parent),
        "supported_channel_modes": ["16ch", "low", "7ch", "5ch"],
        "supported_tta_modes": [True, False],
    }


@app.get("/api/participants")
def list_participants() -> dict[str, Any]:
    inference_manager.load_all()
    participants_out = []
    for subj, spec in PARTICIPANT_SPECS.items():
        golden_list = inference_manager.golden_sessions_by_subject.get(subj, [])
        all_list = inference_manager.sessions_by_subject.get(subj, [])
        off_bundle = inference_manager.offline_models_map.get(subj, {})
        off_metrics = off_bundle["low"].cv_metrics if "low" in off_bundle else {}

        participants_out.append({
            **spec,
            "golden_sessions_count": len(golden_list),
            "total_calibrated_sessions_count": len(all_list),
            "default_session_id": golden_list[0]["session"] if golden_list else "session-01",
            "available_channel_modes": ["16ch", "low", "7ch", "5ch"],
            "offline_cv_metrics": off_metrics,
            "sessions": [
                {
                    "alias": f"session-{idx + 1:02d}",
                    "session_id": e["session"],
                    "date": e["date"],
                    "is_golden_50": bool(e.get("is_golden_50", False)),
                    "n_calib_trials": e["n_calib_trials"],
                    "n_online_trials": e["n_online_trials"],
                    "artgate90_threshold_uv": round(float(e["thr_90_uv"]), 2),
                }
                for idx, e in enumerate(golden_list)
            ],
        })
    return {
        "electrodes_16ch": ELECTRODE_NAMES_16,
        "participants": participants_out,
    }


@app.get("/api/sessions")
def list_sessions(
    participant_id: ParticipantIdLiteral | None = Query(default=None),
    golden_only: bool = Query(default=False, description="Return only the 50 Golden Poster Sessions"),
) -> dict[str, Any]:
    inference_manager.load_all()
    subjects = [participant_id.upper()] if participant_id else ["WMJ", "OYJ", "KGE", "KHY"]
    out_sessions = []
    for subj in subjects:
        source_list = (
            inference_manager.golden_sessions_by_subject[subj]
            if golden_only
            else inference_manager.sessions_by_subject[subj]
        )
        for idx, entry in enumerate(source_list):
            models_info = {}
            for m_key, fm in entry["models"].items():
                models_info[m_key] = {
                    "montage": fm.montage_name,
                    "n_channels": len(fm.ch_idx),
                    "active_channels": fm.active_channels,
                    "band": fm.band_name,
                    "window": fm.win_name,
                    "reg": fm.reg,
                    "tta_enabled": fm.use_ea,
                }
            out_sessions.append({
                "participant_id": subj,
                "korean_name": PARTICIPANT_SPECS[subj]["korean_name"],
                "alias": f"session-{idx + 1:02d}",
                "session_id": entry["session"],
                "date": entry["date"],
                "is_golden_50": bool(entry.get("is_golden_50", False)),
                "is_physical_7ch": bool(entry.get("is_7ch", False)),
                "n_calib_trials": entry["n_calib_trials"],
                "n_online_trials": entry["n_online_trials"],
                "live_in_game_accuracy_pct": round(float(entry["live_acc"]), 2),
                "artgate90_threshold_uv": round(float(entry["thr_90_uv"]), 2),
                "available_models": models_info,
            })
    return {
        "count": len(out_sessions),
        "golden_only": golden_only,
        "sessions": out_sessions,
    }


@app.post("/api/session/init")
@app.post("/api/calibrate")
def calibrate_or_init_session(req: CalibrateSessionRequest) -> dict[str, Any]:
    try:
        return inference_manager.calibrate_custom_or_recorded_session(
            participant_id=req.participant_id,
            session_id=req.session_id,
            channel_mode=req.channel_mode,
            tta_enabled=req.tta_enabled,
            calibration_epochs=req.calibration_epochs,
            calibration_labels=req.calibration_labels,
            client_key="rest",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/predict", response_model=TrialPredictionResponse)
def predict_trial(req: SingleTrialPredictRequest) -> dict[str, Any]:
    try:
        return inference_manager.predict_single_trial(
            participant_id=req.participant_id,
            session_id=req.session_id,
            channel_mode=req.channel_mode,
            tta_enabled=req.tta_enabled,
            protocol=req.protocol,
            trial_index=req.trial_index,
            eeg_data=req.eeg_data,
            is_band_filtered=req.is_band_filtered,
            eog_ptp_uv=req.eog_ptp_uv,
            true_direction=req.true_direction,
            include_waveform=req.include_waveform,
            reset_session_state=req.reset_session_state,
            client_key="rest",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/evaluate/session", response_model=SessionEvaluationResponse)
def evaluate_session(
    req: SessionConfigRequest,
    include_waveforms: bool = Query(default=False, description="Include per-trial active channel EEG waveforms"),
) -> dict[str, Any]:
    try:
        return inference_manager.evaluate_full_session_chronological(
            participant_id=req.participant_id,
            session_id=req.session_id,
            channel_mode=req.channel_mode,
            tta_enabled=req.tta_enabled,
            include_waveforms=include_waveforms,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/replay")
def get_website_replay_source(
    participant_id: ParticipantIdLiteral = Query(default="WMJ"),
    session_id: str = Query(default="session-01"),
    channel_mode: ChannelModeLiteral = Query(default="low"),
    tta_enabled: bool = Query(default=True),
) -> dict[str, Any]:
    """
    Returns a NEUROLINK website `ReplaySource` + full chronological evaluation summary
    for the selected Participant, Session, 16ch/Low Channel, and TTA ON/OFF.
    """
    try:
        res = inference_manager.evaluate_full_session_chronological(
            participant_id=participant_id,
            session_id=session_id,
            channel_mode=channel_mode,
            tta_enabled=tta_enabled,
            include_waveforms=True,
        )
        return res
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/evaluate/cohort")
def evaluate_cohort(
    golden_only: bool = Query(
        default=True,
        description="True evaluates the 50 Golden Poster Sessions; False evaluates all 77 16ch calibrated sessions.",
    ),
) -> dict[str, Any]:
    try:
        return inference_manager.evaluate_cohort_50_sessions_dynamic(golden_only=golden_only)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Real-Time WebSocket Endpoints (/ws/eeg and /ws/inference)
# ---------------------------------------------------------------------------
@app.websocket("/ws/eeg")
@app.websocket("/ws/inference")
async def websocket_eeg_inference(websocket: WebSocket) -> None:
    await websocket.accept()
    client_key = f"ws-{uuid.uuid4().hex[:8]}"

    # Default session state for this WebSocket connection
    ws_config: dict[str, Any] = {
        "participant_id": "WMJ",
        "session_id": "session-01",
        "channel_mode": "low",
        "tta_enabled": True,
        "protocol": "online_calib20",
    }

    # Initialize default session state and send welcome ack
    init_info = inference_manager.calibrate_custom_or_recorded_session(
        participant_id=ws_config["participant_id"],
        session_id=ws_config["session_id"],
        channel_mode=ws_config["channel_mode"],
        tta_enabled=ws_config["tta_enabled"],
        client_key=client_key,
    )
    await websocket.send_json({
        "type": "connected",
        "client_key": client_key,
        "config": ws_config,
        "session_info": init_info,
    })

    try:
        while True:
            msg = await websocket.receive_json()
            action = str(msg.get("action", "step_trial")).strip().lower()

            if action in ("set_config", "init", "configure"):
                ws_config["participant_id"] = str(msg.get("participant_id", ws_config["participant_id"])).upper()
                ws_config["session_id"] = str(msg.get("session_id", ws_config["session_id"]))
                ws_config["channel_mode"] = str(msg.get("channel_mode", ws_config["channel_mode"])).lower()
                if "tta_enabled" in msg:
                    ws_config["tta_enabled"] = bool(msg["tta_enabled"])
                if "protocol" in msg:
                    ws_config["protocol"] = str(msg["protocol"])

                info = inference_manager.calibrate_custom_or_recorded_session(
                    participant_id=ws_config["participant_id"],
                    session_id=ws_config["session_id"],
                    channel_mode=ws_config["channel_mode"],
                    tta_enabled=ws_config["tta_enabled"],
                    client_key=client_key,
                )
                await websocket.send_json({
                    "type": "config_ack",
                    "config": ws_config,
                    "session_info": info,
                })

            elif action == "reset":
                info = inference_manager.calibrate_custom_or_recorded_session(
                    participant_id=ws_config["participant_id"],
                    session_id=ws_config["session_id"],
                    channel_mode=ws_config["channel_mode"],
                    tta_enabled=ws_config["tta_enabled"],
                    client_key=client_key,
                )
                await websocket.send_json({
                    "type": "reset_ack",
                    "session_info": info,
                })

            elif action in ("step_trial", "next_trial", "predict"):
                # Allow per-message overrides of config
                p_id = str(msg.get("participant_id", ws_config["participant_id"])).upper()
                s_id = str(msg.get("session_id", ws_config["session_id"]))
                c_mode = str(msg.get("channel_mode", ws_config["channel_mode"])).lower()
                tta_on = bool(msg["tta_enabled"]) if "tta_enabled" in msg else ws_config["tta_enabled"]
                t_idx = msg.get("trial_index", None)
                inc_wave = bool(msg.get("include_waveform", True))

                rec = inference_manager.predict_single_trial(
                    participant_id=p_id,
                    session_id=s_id,
                    channel_mode=c_mode,
                    tta_enabled=tta_on,
                    protocol=ws_config["protocol"],
                    trial_index=t_idx,
                    eeg_data=msg.get("eeg_data", None),
                    is_band_filtered=bool(msg.get("is_band_filtered", False)),
                    eog_ptp_uv=msg.get("eog_ptp_uv", None),
                    true_direction=msg.get("true_direction", None),
                    include_waveform=inc_wave,
                    reset_session_state=bool(msg.get("reset_session_state", False)),
                    client_key=client_key,
                )
                await websocket.send_json({
                    "type": "trial_prediction",
                    "prediction": rec,
                })

            elif action == "infer_eeg":
                eeg_payload = msg.get("eeg_data") or msg.get("eeg")
                if eeg_payload is None:
                    await websocket.send_json({"type": "error", "detail": "Missing 'eeg_data' array in infer_eeg message"})
                    continue
                rec = inference_manager.predict_single_trial(
                    participant_id=str(msg.get("participant_id", ws_config["participant_id"])).upper(),
                    session_id=str(msg.get("session_id", ws_config["session_id"])),
                    channel_mode=str(msg.get("channel_mode", ws_config["channel_mode"])).lower(),
                    tta_enabled=bool(msg["tta_enabled"]) if "tta_enabled" in msg else ws_config["tta_enabled"],
                    protocol=str(msg.get("protocol", ws_config["protocol"])),
                    eeg_data=eeg_payload,
                    is_band_filtered=bool(msg.get("is_band_filtered", False)),
                    eog_ptp_uv=msg.get("eog_ptp_uv", None),
                    true_direction=msg.get("true_direction", None),
                    include_waveform=bool(msg.get("include_waveform", True)),
                    client_key=client_key,
                )
                await websocket.send_json({
                    "type": "trial_prediction",
                    "prediction": rec,
                })

            elif action == "stream_session":
                p_id = str(msg.get("participant_id", ws_config["participant_id"])).upper()
                s_id = str(msg.get("session_id", ws_config["session_id"]))
                c_mode = str(msg.get("channel_mode", ws_config["channel_mode"])).lower()
                tta_on = bool(msg["tta_enabled"]) if "tta_enabled" in msg else ws_config["tta_enabled"]
                interval_ms = float(msg.get("interval_ms", 50.0))
                speed = max(0.25, float(msg.get("speed", 1.0)))
                delay_s = max(0.0, (interval_ms / 1000.0) / speed)
                inc_wave = bool(msg.get("include_waveform", True))

                full_eval = inference_manager.evaluate_full_session_chronological(
                    participant_id=p_id,
                    session_id=s_id,
                    channel_mode=c_mode,
                    tta_enabled=tta_on,
                    include_waveforms=inc_wave,
                )
                for pred_rec in full_eval["predictions"]:
                    await websocket.send_json({
                        "type": "trial_prediction",
                        "prediction": pred_rec,
                    })
                    if delay_s > 0:
                        await asyncio.sleep(delay_s)

                summary_payload = {k: v for k, v in full_eval.items() if k not in ("predictions", "replay_source")}
                await websocket.send_json({
                    "type": "session_summary",
                    "summary": summary_payload,
                })

            else:
                await websocket.send_json({
                    "type": "error",
                    "detail": f"Unknown WebSocket action '{action}'. Supported: set_config, step_trial, infer_eeg, stream_session, reset.",
                })

    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
    finally:
        for states in (inference_manager.active_online_states, inference_manager.active_offline_states):
            for key in list(states):
                if key.startswith(f"{client_key}::"):
                    states.pop(key, None)
