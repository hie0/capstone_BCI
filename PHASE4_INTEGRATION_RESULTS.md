# Phase 4 — Research Backend Integration

2026-11-14. 기존 전환 커밋 `72ba8fc`에 이어 필요한 지표·Low Channel·Wearable 설정만 추가했다. fetch, 모델 재학습, 기존 백업 재이동, 커밋·푸시는 하지 않았다.

## 실제 연결

- 최종 서버: repo root `backend/`의 FastAPI/WebSocket. 팀원의 5개 joblib과 연구 수학 연산·추론 프로토콜을 유지했다. 모델 파일 SHA256은 전환 전과 동일하다.
- 데이터: `website/capstone_core_handover/online/`. 4명·12세션·540 online trials·240 calibration trials. KGE는 0928_01/0928_02/0930_01이다. 환경변수 `BCI_DATA_ROOT`가 로컬 hint보다 우선한다.
- Smart Home/Wearable의 Participant, 실제 Session, 16ch/Low Channel, TTA, Start/Pause/Reset, 속도, 실제 파형·활성 채널·LEFT/RIGHT를 연결했다. Channel configuration에서는 개별 5ch/7ch 옵션을 제거하고 16ch와 Low Channel만 제공한다. 실제 활성 전극은 모델 응답대로 표시한다.
- 실제 응답의 Decision score=P(RIGHT), raw/centered logit, 추론 latency, Quality Gate 상태·EOG·임계값을 기존 카드 스타일로 표시한다.
- Accuracy/BA는 **현재까지 수신한 trial**의 실제 예측과 기록 정답으로 계산한다. 품질 미달도 포함하며, BA는 양쪽 정답이 관측된 이후 표시한다. Reset/설정 변경 시 초기화한다. 발표 성능을 채워 넣지 않는다.
- Quality Gate PASS인 실제 모델 예측만 스마트홈 명령·장치 상태·Command History로 전달한다. Ground Truth는 평가에만 사용한다. Backend 오류를 synthetic으로 대체하지 않는다.
- CSS, 3D 모델/장면 형상, 페이지 구성, Home/Research, 기존 발표자료·연구 결과 데이터는 변경하지 않았다.

## 검증 및 로컬 실행

| 항목 | 실제 결과 |
|---|---|
| 기존 검증 재사용 | 실제 joblib 5개 로딩, Health, 12세션 연결, 48회 세션 평가/2160 trial 조건, 4명 WebSocket, 연결별 TTA 상태·탐색 검증 통과 |
| 이번 추가 API 검증 | 4명 × Low TTA OFF/ON × 3 chronological trials = 24회. joblib 직접 추론과 HTTP 응답의 확률·logit·활성 채널·Quality Gate 일치 |
| 브라우저 추가 검증 | Phase4 지표/Low/Wearable, 기존 Recorded 장치 제어/Replay, 연결 실패 처리: 3개 통과 |
| 마지막 회귀 검증 | 기존 Wearable 상태 공유, 3D/5·7ch 선택, 최종 Phase4 시나리오: 3개 통과 |
| 화면 | Smart Home/Wearable 390/1024/1440px 가로 overflow 없음. 1440px 실제 렌더 캡처 확인 |
| 빌드 | TypeScript/Vite 성공. 기존 Three.js 번들 크기 경고만 있음 |
| 하드웨어 | 물리/논리 CPU 각 8코어, RAM 8GiB (`sysctl` 실제 확인) |
| 병렬 처리 | 독립 EEG 세션 로딩 2스레드, 추가 독립 모델 검증 2 Python 프로세스. 세션 내부 Causal EA/Logit Centering은 순차 처리 |
| 중첩 스레드 | Backend 진입 시 BLAS/OMP/MKL/Accelerate/NumExpr 각 1스레드. 검증 프로세스의 BLAS 풀도 실제 모두 1스레드 확인 |

모델은 메모리에서 재사용하고, 이미 완료한 전수 검증은 다시 돌리지 않았다. 원본 CSV 내용은 AI 컨텍스트에 넣지 않았다. 상세 로그·수치·스크린샷은 Git에서 제외한 `backend/local_cache/phase4/`, `phase4-*.log` 및 기존 `local_cache/migration/`에 저장했다.

추가 검증 코드: `backend/validate_phase4.py`, `website/tests/phase4.spec.ts`. 실행 방법은 `backend/LOCAL_SETUP.md`를 따른다.

## 연구 조건 및 남은 한계

현재 UI의 Recorded EEG는 **세션별 사전 export된 Calib20 모델의 연구 재생**이다. 4명 offline champion도 로드되지만 현재 UI에서 서로 섞지 않는다. 50세션 사후 최적 조건 선택 성능이나 사전 고정 모델의 독립적인 실시간 테스트 성능으로 주장하지 않는다.

특히 제공된 `low` 키는 TTA ON/OFF 간에도 다른 montage를 포함한다. 이번 각 피험자의 첫 로컬 세션 확인 결과:

| 피험자 / 확인 세션 | Low TTA OFF | Low TTA ON |
|---|---|---|
| WMJ / wmj_online0928_01 | 7ch_PM_NoCAR | 6ch_PM_NoCAR |
| KGE / kge_online0928_01 | 5ch_Core_NoCAR | 7ch_PM_LocCAR |
| OYJ / oyj_online0929_02 | 7ch_PM_LocCAR | 7ch_PM_LocCAR |
| KHY / khy_online0928_02 | 7ch_PM_LocCAR | 7ch_PM_LocCAR |

WMJ의 6ch는 기존 연구용 PM 구성을 임의 변경한 것이 아니라 제공된 joblib의 해당 Low 모델 그대로다. KGE의 5ch_Core는 C3/Cz/C4/P7/P8이며 연구용 F3/F4/C3/Cz/C4와 구분한다. UI는 실제 활성 채널을 표시한다. 이 Low 비교는 TTA 단독 효과 비교가 아니다. 고정 모델 실시간 검증에는 팀원이 확정한 동일 조건 모델과 사전 고정된 전처리/품질 기준이 별도로 필요하다. 모델을 새로 구현하거나 재학습해서 이 차이를 숨기지 않았다.

ArtGate90은 팀원 모델에 저장된 사후 임계값을 그대로 사용한다. 시간순 추론이라고 해도 이 임계값을 독립적인 사전 고정 라이브 품질 기준으로 해석하지 않는다. 웹사이트의 장치는 가상 3D 장치이며 실제 가전/EEG 수집 하드웨어 연결은 아니다.

GitHub Pages에는 Python 서버가 호스팅되지 않는다. 외부 Recorded EEG 사용은 별도 Backend 호스팅 및 `VITE_BCI_API_BASE` 또는 reverse proxy가 필요하다.

## 기존 백업 보존

기존 계획의 13개 경로/712개 파일은 이미 저장소 외부 `capstone_backup/backend-migration-20261114-200232/`로 이동돼 있다. 이번에 추가로 옮긴 경로는 없다.

모든 백업 파일, 보존 대상 142개 파일, 신규 joblib 5개의 SHA256을 다시 확인했다. 원본 EEG·common_model·발표자료·포스터는 보존했다. 기존 `MIGRATION_MANIFEST.json`과 `RESTORE.md`는 그대로 유지한다. 상세 경로는 [BACKEND_MIGRATION.md](BACKEND_MIGRATION.md)에 있다.

현재 로컬 웹사이트: http://127.0.0.1:5173/#/simulation — `Input mode → Recorded EEG` 선택. API: http://127.0.0.1:8000/api/health.
