# -*- coding: utf-8 -*-
"""
Pydantic Schemas for NEUROLINK EEG FastAPI & WebSocket Backend
==============================================================
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

ParticipantIdLiteral = Literal["WMJ", "KGE", "OYJ", "KHY"]
ChannelModeLiteral = Literal["16ch", "low", "7ch", "5ch"]
DirectionLiteral = Literal["LEFT", "RIGHT"]


class QualityAssessment(BaseModel):
    is_clean: bool = Field(..., description="Whether trial passes ArtGate90 frontal/temporal EOG check")
    status: Literal["PASS", "ARTIFACT_GATED"] = Field(..., description="Quality gate judgment")
    gate_name: str = Field(default="ArtGate90", description="Quality gate algorithm")
    eog_ptp_uv: float = Field(..., description="Measured peak-to-peak amplitude on Fp1/Fp2/F7/F8 in uV")
    threshold_uv: float = Field(..., description="Session 90th-percentile artifact threshold in uV")


class TTAStateInfo(BaseModel):
    accumulated_trials: int = Field(..., description="Number of chronological trials processed so far (1..t)")
    running_logit_bias: float = Field(..., description="Current CausalLogitCenter running bias offset")
    cov_condition_log10: float = Field(..., description="Covariance matrix condition number log10(kappa)")
    band: str = Field(..., description="Active frequency band")
    window: str = Field(..., description="Active multi-crop time window configuration")
    reg: float | None = Field(default=None, description="Regularized CSP shrinkage parameter")


class TrialPredictionResponse(BaseModel):
    trial_id: int = Field(..., description="1-based chronological trial index")
    trialId: int = Field(..., description="Frontend-compatible alias for trial_id")
    step_index: int = Field(..., description="Sequential step counter in the active TTA session")
    timestamp: float = Field(..., description="Trial onset timestamp in seconds")
    participant_id: ParticipantIdLiteral
    session_id: str
    model_id: str
    modelId: str
    model_name: str
    channel_mode: str
    channelSet: str
    montage: str
    n_channels: int
    active_channels: list[str]
    tta_enabled: bool
    predicted_direction: DirectionLiteral
    predictedLabel: DirectionLiteral
    true_direction: DirectionLiteral | None = None
    trueLabel: DirectionLiteral | None = None
    is_correct: bool | None = None
    decision_score: float = Field(..., description="Model decision score (sigmoid probability for RIGHT in [0, 1])")
    score: float = Field(..., description="Frontend-compatible alias for decision_score")
    probability_right: float
    probability_left: float
    raw_logit: float = Field(..., description="Uncentered classifier decision_function logit")
    calibrated_logit: float = Field(..., description="CausalLogitCenter-adjusted logit")
    latency_ms: float = Field(..., description="Actual measured inference wall-clock latency in milliseconds")
    quality: QualityAssessment
    tta_state: TTAStateInfo
    waveform: dict[str, list[float]] | None = Field(
        default=None,
        description="Optional real EEG waveform snippet (uV) for active channels on this trial",
    )


class SessionConfigRequest(BaseModel):
    participant_id: ParticipantIdLiteral = Field(default="WMJ", description="Participant ID (WMJ, KGE, OYJ, KHY)")
    session_id: str = Field(
        default="session-01",
        description="Session ID (exact session folder name or alias like 'session-01', 'golden-01')",
    )
    channel_mode: ChannelModeLiteral = Field(
        default="low",
        description="Channel mode: '16ch', 'low' (participant optimal low-channel), '7ch', or '5ch'",
    )
    tta_enabled: bool = Field(
        default=True,
        description="Enable CausalEA + CausalLogitCenter Test-Time Adaptation",
    )
    protocol: Literal["online_calib20", "offline_champion"] = Field(
        default="online_calib20",
        description="Inference protocol: 'online_calib20' (Same-Day Calib20 + Multi-Crop) or 'offline_champion'",
    )


class SingleTrialPredictRequest(BaseModel):
    participant_id: ParticipantIdLiteral = Field(default="WMJ")
    session_id: str = Field(default="session-01")
    channel_mode: ChannelModeLiteral = Field(default="low")
    tta_enabled: bool = Field(default=True)
    protocol: Literal["online_calib20", "offline_champion"] = Field(default="online_calib20")
    trial_index: int | None = Field(
        default=None,
        description="0-based chronological trial index from the selected recorded session (if eeg_data not sent)",
    )
    eeg_data: list[list[float]] | None = Field(
        default=None,
        description="Optional raw or band-filtered 2D EEG array of shape (C, T) or (T, C) in uV",
    )
    is_band_filtered: bool = Field(
        default=False,
        description="When eeg_data is provided: True if already band-filtered, False if raw broadband EEG (uV)",
    )
    eog_ptp_uv: float | None = Field(
        default=None,
        description="Optional pre-computed frontal/temporal EOG peak-to-peak amplitude in uV",
    )
    true_direction: DirectionLiteral | None = Field(default=None)
    include_waveform: bool = Field(default=False, description="Include downsampled channel waveforms in response")
    reset_session_state: bool = Field(default=False, description="Reset causal TTA accumulator before this trial")


class CalibrateSessionRequest(BaseModel):
    participant_id: ParticipantIdLiteral = Field(default="WMJ")
    session_id: str = Field(default="custom-session")
    channel_mode: ChannelModeLiteral = Field(default="low")
    tta_enabled: bool = Field(default=True)
    calibration_epochs: list[list[list[float]]] | None = Field(
        default=None,
        description="Optional 3D array (N_cal, 16, 500) of raw calibration EEG epochs in uV. If omitted, uses the recorded session's 20 calibration trials.",
    )
    calibration_labels: list[DirectionLiteral | int] | None = Field(
        default=None,
        description="Labels ('LEFT'/'RIGHT' or 0/1) for calibration_epochs",
    )


class SessionEvaluationResponse(BaseModel):
    participant_id: ParticipantIdLiteral
    korean_name: str
    session_id: str
    resolved_session_name: str
    date: str
    is_golden_50: bool
    channel_mode: str
    montage: str
    n_channels: int
    active_channels: list[str]
    tta_enabled: bool
    model_id: str
    model_name: str
    total_trials: int
    clean_trials_artgate90: int
    artifact_gated_trials: int
    live_in_game_accuracy_pct: float | None
    computed_metrics_artgate90: dict[str, float]
    computed_metrics_all_trials: dict[str, float]
    mean_latency_ms: float
    predictions: list[TrialPredictionResponse]
    replay_source: dict[str, Any] = Field(
        ...,
        description="NEUROLINK website ReplaySource-compatible payload ({kind: 'recorded', predictions, frames, sampleRateHz})",
    )
