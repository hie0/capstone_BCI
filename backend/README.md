# NEUROLINK Real-Time MI-BCI Research Backend (`research-backend`)

최종 발표자료 및 캡스톤 포스터의 **4인 피험자 오프라인 평가(LOSO / LORO / 10-Fold CV)** 및 **50세션 실전 온라인 평가(Same-Day Calib20 + Multi-Crop + CausalEA + CausalLogitCenter + ArtGate90)** 성능을 산출한 **실제 연구 코드와 학습된 모델(`joblib`)**을 NEUROLINK 웹사이트에서 실시간으로 호출할 수 있도록 구현한 **FastAPI + WebSocket 백엔드**입니다.

---

## 1. 기존 Bundle과의 차이점 및 성능 재현 원리

초기 전달된 `model/<subj>_model.joblib` (`bci_bundle_v1`)은 0.5초 단일 윈도우 및 고정 임계값을 사용한 초기 베이스라인 모델이었습니다.  
최종 발표자료의 핵심 성능은 다음 **두 가지 실제 연구 파이프라인**에서 산출되었으며, 본 백엔드는 이 두 파이프라인의 **실제 실행 코드와 학습된 상태(fitted state)**를 그대로 사용합니다.

1. **50세션 실전 온라인 평가 (`Same-Day Calib20 + Multi-Crop + CausalEA + CausalLogitCenter + ArtGate90`)**
   - 실행 스크립트: `backend/research_scripts/run_4subj_calib_online_master.py`
   - 신호 전처리: $f_s = 250\text{ Hz}$, $60\text{ Hz}$ IIR Notch ($Q=30$) + 4차 Butterworth 대역통과 필터 (`mu`: 8–13 Hz, `extmu`: 8–15 Hz, `himu`: 10–15 Hz)
   - 당일 20회 캘리브레이션 보정(`Calib20`) + Multi-Crop Ensemble (`W_1.5s_Multi`: `[0:250], [62:312], [125:375]`, `W_1.0s_Dual`: `[0:125], [125:250]`, `W_2.0s_Single`: `[0:500]`)
   - 공간 필터 및 분류기: Regularized CSP ($\lambda \in \{0.05, 0.15\}$, $n_{\text{comp}}=4$) + Shrinkage LDA (`solver="lsqr", shrinkage="auto"`)
   - 인과적 테스트 시점 적응(Causal TTA):
     - **CausalEA (인과적 유클리드 공분산 백색화)**: 당일 캘리브레이션 공분산 $R_{\text{cal}}$로 예열($R_{\text{init}} = 8.0 \cdot R_{\text{cal}}, w_0 = 8.0$)한 뒤, 매 온라인 트라이얼 $t = 1, 2, \dots, N$이 시간 순서대로 들어올 때마다 누적 공분산 $R_m^{(t)} = \frac{0.2(I/C) + R_{\text{sum}}^{(t)}}{w_0 + t}$를 갱신하고 $X_t \leftarrow (R_m^{(t)})^{-1/2} X_t$ 백색화 수행
     - **CausalLogitCenter (인과적 로짓 영점 정렬)**: 매 트라이얼의 결정 함수 로짓 $z_t$에서 누적 평균 편향 $\hat{b}_t = \frac{\sum_{k=1}^t z_k}{3.0 + t}$을 실시간 차감한 뒤 시그모이드 확률 $p_t = \sigma(z_t - \hat{b}_t)$ 산출
   - **품질 게이트 (`ArtGate90`)**: 전두·측두 안구/안면 근전도 전극(`Fp1, Fp2, F7, F8`)의 $[0, 1.5\text{s}]$ 구간 Peak-to-Peak 진폭($\mu\text{V}$)을 측정하여 세션 90백분위 임계값 이하 여부를 판정

2. **4인 피험자별 오프라인 챔피언 모델 (`LOSO / LORO / 10-Fold CV`)**
   - 실행 스크립트: `backend/research_scripts/run_8core_turbo_boost.py`
   - **WMJ**: `7ch_PM_NoCAR` (`F3, F4, C3, Cz, C4, P7, P8`), `Riemann_TS_sLDA` / `CSP_WelchPSD_sLDA` + `CausalEA` + `CausalLogitCenter`
   - **KGE**: `5ch_PM_NoCAR` (`F3, F4, C3, Cz, C4`), `OAS + Ensure-SPD + Log-Euclidean Riemann TS + sLDA` + `CausalEA` + `CausalLogitCenter`
   - **OYJ**: `5ch_PM_NoCAR` / `6ch_PM_LocCAR` / `7ch_PM_LocCAR`, `Riemann_TS_sLDA` & `SuperHybrid_TS_CSP_ERD` (`0.55 * RiemannTS + 0.45 * Reg-CSP/WelchPSD/ERD`) + `ArtGate90` + `CausalEA` + `CausalLogitCenter`
   - **KHY**: `6ch_PM_LocCAR` / `7ch_PM_LocCAR`, `ArtGate90` + `broad_8_35` + `Ensure-SPD OAS + SuperHybrid_TS_CSP_ERD` + `CausalEA` + `CausalLogitCenter`

---

## 2. 디렉토리 구조 및 Export된 모델 (`joblib`)

원본 EEG 파형(`.csv`, `.pkl`) 및 개인정보는 공개 저장소에 절대 업로드되지 않으며(`.gitignore` 처리), 학습된 모델 파라미터(공간 필터 행렬 $W$, 공분산 기준점 $R_{\text{cal}}$, 스케일러, 분류기 가중치)만 `backend/models/*.joblib`으로 저장되어 있습니다.

```text
backend/
├── __init__.py
├── app.py                          # FastAPI + WebSocket 서버 메인 엔트리포인트
├── inference_engine.py             # 실시간/시간순 EEG 추론 및 세션/코호트 동적 평가 엔진
├── research_protocol.py            # 실제 연구 신호처리, Calib20, CausalEA, CausalLogitCenter, 모델 클래스
├── schemas.py                      # REST / WebSocket 입출력 Pydantic 스키마
├── export_and_verify_models.py     # 실제 연구 데이터 기반 성능 재검증 및 joblib Export 스크립트
├── verify_api_and_websocket.py     # REST API 및 WebSocket 전수 자동 검증 스크립트
├── requirements.txt                # Python 실행 환경 패키지 명세
├── models/                         # Joblib으로 Export된 학습 완료 모델 상태 (원본 EEG 미포함)
│   ├── wmj_final_model.joblib
│   ├── kge_final_model.joblib
│   ├── oyj_final_model.joblib
│   ├── khy_final_model.joblib
│   ├── online_50sessions_calib_models.joblib
│   └── verification_summary.json
└── research_scripts/               # 최종 발표 수치를 생성한 실제 연구 스크립트 원본
    ├── run_4subj_calib_online_master.py
    └── run_8core_turbo_boost.py
```

---

## 3. 실행 환경 및 서버 구동 방법

### 3.1 Python 환경 설정
- 검증된 연구 환경: Python 3.11 (`conda` 환경 `bci`)
- 의존성 설치:
  ```powershell
  pip install -r backend/requirements.txt
  ```

### 3.2 로컬 원본 EEG 데이터 경로 설정 (`BCI_DATA_ROOT`)
원본 EEG CSV 데이터는 공개 저장소에 포함되지 않으므로, 로컬 연구 머신의 데이터 경로를 `BCI_DATA_ROOT` 환경변수로 지정합니다:
```powershell
$env:BCI_DATA_ROOT = "C:\path\to\local\capstone\data"
```

### 3.3 성능 재검증 및 모델 Export 실행
```powershell
python backend/export_and_verify_models.py
```

### 3.4 FastAPI + WebSocket 서버 실행
```powershell
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```
- Swagger UI (대화형 API 문서): `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/api/health`

### 3.5 REST & WebSocket 통합 검증 테스트 실행
```powershell
python backend/verify_api_and_websocket.py
```

---

## 4. API 명세 (REST & WebSocket)

> **주의**: 모든 API 응답은 발표자료의 수치를 하드코딩하지 않으며, 입력된 실제 EEG 파형 `(C, T)`에 대해 실시간 공간 필터링 + `CausalEA` + `CausalLogitCenter` + 분류기 추론을 수행하여 동적으로 계산됩니다.

### 4.1 `GET /api/participants`
선택 가능한 피험자(`WMJ`, `KGE`, `OYJ`, `KHY`), 최적 채널 구성(`7ch`/`5ch`), 모델 정보 및 세션 목록을 반환합니다.

### 4.2 `GET /api/sessions?participant_id=WMJ&golden_only=true`
피험자별 선택 가능한 실전 온라인 세션(50개 골든 세션 또는 전체 79개 보정 세션) 목록과 각 세션의 `ArtGate90` 임계값($\mu\text{V}$), 지원 채널 모드를 반환합니다.
- 웹사이트 드롭다운의 `"session-01"`, `"session-02"` 별칭(alias)과 실제 세션 폴더명(`"wmj_online0928_01"` 등)을 모두 지원합니다.

### 4.3 `POST /api/calibrate` (또는 `POST /api/session/init`)
선택한 `(participant_id, session_id, channel_mode, tta_enabled)` 조합으로 시간순(Chronological) TTA 세션 상태를 초기화하거나, 새로운 20회 캘리브레이션 원시 EEG(`calibration_epochs`: `(20, 16, 500)`)를 입력받아 실시간 `Same-Day Calib20 + Multi-Crop` 모델을 학습합니다.

### 4.4 `POST /api/predict` — 단일 트라이얼 시간순 EEG 추론
실제 EEG 데이터(`eeg_data` 2차원 배열 `(16, 500)`) 또는 선택된 세션의 시간순 트라이얼 인덱스(`trial_index`)를 입력받아 `LEFT` / `RIGHT` 예측 및 세부 지표를 반환합니다.

**Request Body 예시:**
```json
{
  "participant_id": "WMJ",
  "session_id": "session-01",
  "channel_mode": "low",
  "tta_enabled": true,
  "trial_index": 0,
  "include_waveform": true
}
```

**Response 예시:**
```json
{
  "trial_id": 1,
  "trialId": 1,
  "step_index": 1,
  "timestamp": 282.584,
  "participant_id": "WMJ",
  "session_id": "wmj_online0928_01",
  "model_id": "wmj-reg-csp",
  "model_name": "Regularized CSP + Welch PSD + sLDA (6ch_PM_NoCAR)",
  "channel_mode": "low",
  "montage": "6ch_PM_NoCAR",
  "n_channels": 6,
  "active_channels": ["F3", "F4", "C3", "Cz", "C4", "Pz"],
  "tta_enabled": true,
  "predicted_direction": "LEFT",
  "predictedLabel": "LEFT",
  "true_direction": "LEFT",
  "trueLabel": "LEFT",
  "is_correct": true,
  "decision_score": 0.104124,
  "score": 0.104124,
  "probability_right": 0.104124,
  "probability_left": 0.895876,
  "raw_logit": -2.648102,
  "calibrated_logit": -2.152218,
  "latency_ms": 0.632,
  "quality": {
    "is_clean": true,
    "status": "PASS",
    "gate_name": "ArtGate90",
    "eog_ptp_uv": 206.86,
    "threshold_uv": 860.88
  },
  "tta_state": {
    "accumulated_trials": 1,
    "running_logit_bias": -0.495884,
    "cov_condition_log10": 1.6842,
    "band": "himu",
    "window": "W_1.5s_Multi",
    "reg": 0.05
  }
}
```

### 4.5 `POST /api/evaluate/session` & `GET /api/replay`
선택한 세션의 전체 트라이얼($t = 1 \dots N$)을 시간 순서대로 추론하여 매 트라이얼의 예측 결과, 동적으로 계산된 세션 정확도(`balanced_accuracy_pct`, `accuracy_pct`, `roc_auc`), 그리고 NEUROLINK 웹사이트의 `ReplaySource` 포맷(`{kind: "recorded", predictions, frames, sampleRateHz}`)을 함께 반환합니다.

### 4.6 `GET /api/evaluate/cohort?golden_only=true`
50개 골든 세션(또는 77개 16ch 보정 세션 전체)의 모든 온라인 트라이얼을 시간 순서대로 실제 추론하여 피험자별·전체 코호트 평균 Balanced Accuracy, ROC-AUC, 대응 표본 $t$-검정 및 Wilcoxon 부호순위 검정 $p$-value를 동적으로 산출합니다.

### 4.7 `WS /ws/eeg` (또는 `WS /ws/inference`) — 실시간 WebSocket 스트리밍
웹사이트와 양방향 JSON 메시지를 주고받으며 실시간 설정 변경 및 시간순 EEG 추론을 수행합니다.
- **설정 변경 (`set_config`)**:
  ```json
  {
    "action": "set_config",
    "participant_id": "KGE",
    "session_id": "session-01",
    "channel_mode": "5ch",
    "tta_enabled": true
  }
  ```
- **다음 시간순 트라이얼 추론 (`step_trial`)**:
  ```json
  {
    "action": "step_trial",
    "include_waveform": true
  }
  ```
- **원시 EEG 배열 실시간 추론 (`infer_eeg`)**:
  ```json
  {
    "action": "infer_eeg",
    "eeg_data": [[...], [...]],
    "is_band_filtered": false,
    "include_waveform": true
  }
  ```
- **세션 전체 실시간 연속 스트리밍 (`stream_session`)**:
  ```json
  {
    "action": "stream_session",
    "speed": 1.0,
    "interval_ms": 100,
    "include_waveform": true
  }
  ```

---

## 5. 실제 연구 환경 성능 재검증 결과 요약

`python backend/export_and_verify_models.py` 및 `GET /api/evaluate/cohort?golden_only=true`를 통해 Export된 `.joblib` 모델과 시간순 추론 엔진(`StatefulOnlineTTASession`)에서 직접 재검증된 결과입니다.

### 5.1 50세션 실전 온라인 평가 재검증 결과 (`N = 50 Golden Sessions`)

| 피험자 | 세션 수 (대상 일자) | ① 현장 라이브 | ② 16ch (TTA OFF) | ③ 16ch (TTA ON) | ④ Low-Ch (TTA OFF) | ⑤ **Low-Ch (TTA ON)** | 현장 대비 ($\Delta$) | 16ch 대비 ($\Delta$) | 대응 $t$-검정 ($p$-value) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **WMJ** | 13 (`0928,0930,1001,1007`) | 55.58% | 72.26% | 72.68% | 76.03% | **76.77%** | +21.20%p | +4.51%p | $t = 2.406, p = 0.0332^*$ |
| **OYJ** | 9 (`0929,0930,1002,1007`) | 57.22% | 75.11% | 75.17% | 78.50% | **81.83%** | +24.61%p | +6.72%p | $t = 2.691, p = 0.0275^*$ |
| **KGE** | 13 (`0928,0930,1001,1007`) | 54.10% | 67.55% | 69.27% | 69.84% | **72.83%** | +18.73%p | +5.28%p | $t = 2.928, p = 0.0126^*$ |
| **KHY** | 15 (`0928,0930,1001,1006,1008`) | 51.00% | 62.18% | 63.32% | 63.98% | **67.23%** | +16.23%p | +5.05%p | $t = 3.862, p = 0.0017^{**}$ |
| **4인 코호트 평균** | **50 Sessions** | **54.48%** | **69.28%** | **70.11%** | **72.09%** | **74.66%** | **+20.19%p** | **+5.39%p** | **$t = 5.999, p = 2.35 \times 10^{-7}$** |

### 5.2 피험자별 오프라인 챔피언 모델 재검증 결과 (`backend/models/<subj>_final_model.joblib`)

| 피험자 | Export 모델 파일 | 최적 저채널 몽타주 | 활성 전극 | 모델 아키텍처 | LOSO Balanced Acc | LOSO ROC-AUC |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: |
| **WMJ** | `wmj_final_model.joblib` | `7ch_PM_NoCAR` | `F3, F4, C3, Cz, C4, P7, P8` | `Riemann_TS_sLDA` / `CSP_WelchPSD_sLDA` | **83.33%** | **0.8838** |
| **KGE** | `kge_final_model.joblib` | `5ch_PM_NoCAR` | `F3, F4, C3, Cz, C4` | `OAS + Riemann_TS_sLDA` | **83.33%** | **0.8733** |
| **OYJ** | `oyj_final_model.joblib` | `5ch_PM_NoCAR` | `F3, F4, C3, Cz, C4` | `Riemann_TS_sLDA` / `SuperHybrid` | **73.26%** | **0.7958** |
| **KHY** | `khy_final_model.joblib` | `6ch_PM_LocCAR` | `F3, F4, C3, C4, P7, P8` | `ArtGate90 + SuperHybrid_TS_CSP_ERD` | **68.97%** | **0.7105** |
