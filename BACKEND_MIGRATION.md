# Backend 전환 및 백업 완료 기록

가져온 브랜치: research-backend (`7aa160be59df`)

백업 위치(저장소 외부): `/Users/kimhieyoung/Desktop/capstone_data/capstone_backup/backend-migration-20261114-200232`

현재 상태: 신규 Backend·웹사이트 연결 및 백업 완료. 기존 파일을 이동한 뒤 서버를 새로 시작하고 실제 API·WebSocket·브라우저 검증을 다시 통과했다.

## 의존성 확인

- 기존 웹사이트는 기존 website/backend/ 및 재현 모델을 import하거나 호출하지 않았다. 현재까지 입력은 manual/synthetic이었다.
- 신규 backend/는 backend.research_protocol 및 자체 joblib만 사용한다. 기존 연구 Backend·모델·연구 CSV에 대한 런타임 의존성은 없다.
- 신규 Recorded EEG 로더의 유일한 EEG 루트는 website/capstone_core_handover/online/이다. 이 경로는 이동하지 않는다.
- 기존 website/backend/의 Python은 models_final/, models_reproduced/ 및 Handover 연구 코드에 의존한다. 서로 같은 상대 경로로 함께 백업한다.
- 원본 ExG/Marker/Meta/ORN/Calibration/Online 로그, common_model/ 전체, 원본 연구 문서와 GLB는 보존한다.
- Bundle의 README·가이드·보고서·포스터 MD와 모든 PDF/PPTX는 원래 위치에 남긴다. baseline_online_bundle 안에서도 코드·모델·requirements만 이동한다.
- repo root의 Unity, model/, 기존 장비 실행 코드는 이번 이동 범위에 포함하지 않는다.

## 정확한 이동 대상

| 원본(저장소 상대경로) | 파일 수(캐시 포함) | 크기 |
|---|---:|---:|
| `website/backend` | 92 | 7.39 MiB |
| `website/models_final` | 195 | 5.83 MiB |
| `website/models_reproduced` | 357 | 11.32 MiB |
| `website/capstone_core_handover/scripts` | 19 | 0.32 MiB |
| `website/capstone_core_handover/results_csv` | 12 | 7.46 MiB |
| `website/capstone_core_handover/models` | 10 | 1.81 MiB |
| `website/capstone_core_handover/bci_reproduction_and_baseline_bundle/scripts` | 10 | 0.29 MiB |
| `website/capstone_core_handover/bci_reproduction_and_baseline_bundle/results_csv` | 9 | 2.84 MiB |
| `website/capstone_core_handover/bci_reproduction_and_baseline_bundle/baseline_online_bundle/model` | 4 | 1.76 MiB |
| `website/capstone_core_handover/bci_reproduction_and_baseline_bundle/baseline_online_bundle/neuro_feedback3.py` | 1 | 0.05 MiB |
| `website/capstone_core_handover/bci_reproduction_and_baseline_bundle/baseline_online_bundle/neuro_feedback3_calibrated.py` | 1 | 0.07 MiB |
| `website/capstone_core_handover/bci_reproduction_and_baseline_bundle/baseline_online_bundle/ensure_spd.py` | 1 | 0.00 MiB |
| `website/capstone_core_handover/bci_reproduction_and_baseline_bundle/baseline_online_bundle/requirements.txt` | 1 | 0.00 MiB |

파일별 SHA256 및 보존 대상 해시는 backend/local_cache/migration/plan.json에 있다.
이동 전후 712개 파일의 SHA256을 확인했다. 보존 대상 142개 파일과 신규 Backend의 5개 joblib도 해시가 동일하다.
백업 루트의 MIGRATION_MANIFEST.json에 모든 원본·대상 경로와 SHA256이 있고 RESTORE.md에 복원 방법이 있다. 커밋·푸시는 하지 않았다.


## 신규 Backend와 데이터 연결

- research-backend의 backend/만 가져왔으며 현재 브랜치는 game이다. 브랜치 전체 merge/reset은 하지 않았다.
- backend/.venv에 모델과 같은 sklearn 1.9.1을 설치했다. 실제 환경은 backend/requirements-lock.txt에 기록했다.
- 4명의 final joblib과 online_50sessions_calib_models.joblib을 실제 로드했다. 기존 joblib은 재학습하거나 덮어쓰지 않았다.
- 원래 Backend는 BCI_DATA_ROOT 대신 별도 pickle 캐시를 사용했다. 독립 로더 backend/recorded_data.py를 추가하여 기존 온라인 원본 CSV를 직접 읽도록 했다. 이전 연구 코드를 import하지 않는다.
- 로컬 데이터 루트: website/capstone_core_handover/online/. BCI_DATA_ROOT 환경변수가 우선이고 이 컴퓨터의 경로는 git에서 제외한 backend/local_cache/data_root.txt에 기록했다.
- 4명·12세션·540 online trials·240 calibration trials의 ExG/Marker/Meta/ORN 및 calibration/online 로그를 보존한다. 250Hz, 16채널, Marker/로그 정렬, MI 길이를 검증했다.
- 직렬화 모델 카탈로그의 79세션과 원본 EEG가 실제 존재하는 12세션을 구분한다. API에는 사용 가능한 로컬 세션만 노출한다.
- 없는 세션이나 없는 채널/TTA 조합은 오류로 응답한다. 다른 모델이나 세션으로 자동 대체하지 않는다.

## 웹사이트 연결과 연구 조건 구분

- 디자인·CSS·3D 모델 파일·기존 연구 결과 데이터·Home/Research 페이지는 변경하지 않았다.
- 응용/Replay의 기존 공통 상태에 Recorded EEG 입력을 연결했다. Participant/Session/채널/TTA/속도, 실제 파형·confidence·명령·재생/일시정지/초기화·탐색을 연결했다.
- 전극 강조는 실제 모델의 active_channels를 사용한다. 채널 수만 보고 PM Core/Extended의 고정 전극 목록으로 가장하지 않는다.
- 신규 세션별 추론은 Calib20의 Regularized CSP+sLDA다. 기존 발표용 Hybrid/SVC 모델명과 구분하여 실제 모델명을 표시한다.
- 신규 직렬화 모델에는 원래 PM Core/Extended와 다른 montage도 포함된다. 5/7ch 선택은 실제 5/7ch 키를 요청하며 low 키의 6ch 등으로 대체하지 않는다. 기존 연구 페이지의 역사적 채널 구성과 수치는 유지했다.
- WebSocket 연결별 TTA 상태를 분리한다. 일시정지 후 기존 trial 위치까지 순서대로 복원한다. 오류 시 합성 EEG로 대체하지 않으며 품질 기준 미달 trial은 모니터에만 표시하고 장치 명령을 보류한다.
- 기존 Drei Html 전극 라벨의 빠른 화면 전환 시 DOM 제거 오류를 안정된 portal로 수정했다. 모델 형상·카메라·조명은 바꾸지 않았다.
- 이 검증은 기존 Backend의 모델·원본 EEG·웹사이트 간 실행 검증이다. 사전 선택 세션/품질 임계값을 포함하는 기존 프로토콜의 결과를 새 독립 테스트 성능이라고 주장하지 않는다.

## 검증 결과

- 실제 API: 12세션 × 16ch/저채널 × TTA OFF/ON = 48회 전체 세션 평가, 총 2160 trial 조건 통과.
- 4명 WebSocket 추론, 두 클라이언트 상태 독립성, 앞뒤 탐색 재현성, 실제 raw EEG tensor 추론, 진단용 정답 변경의 예측 불변성, 알 수 없는 세션 거부를 확인했다.
- npm run build: TypeScript 검사·Vite 빌드 통과. 기존 Three.js 번들 크기 경고만 있다.
- Chrome Playwright 전체 8개 시나리오 통과. 수동/합성 모드·장치 제어·3D 전극·공유 설정·Home/Research·WebGL fallback·Recorded EEG·오류 처리를 확인했다.
- Recorded 화면은 390/768/1024/1440px에서 가로 overflow가 없는지 확인했다.
- 백업 후 신규 서버를 완전히 재시작하여 위 48회 API 평가와 WebSocket 검증을 다시 통과했다. Recorded 브라우저 테스트 2개도 다시 통과했다.
- 기존 테스트가 생성한 추적 스크린샷은 원래 바이트로 복원했다. 새 실제 EEG 스크린샷은 비공개 backend/local_cache/migration/recorded-home-1440-final.png 및 recorded-replay-1440.png에 있다.
- 근거: backend/local_cache/migration/api_validation.json, browser_validation.json, completed.json. 원본 데이터와 개인 경로가 포함된 캐시는 Git에서 제외한다.

## 실행 및 복원

실행 안내: [backend/LOCAL_SETUP.md](backend/LOCAL_SETUP.md).
현재 로컬 웹사이트는 http://127.0.0.1:5173/#/simulation, 신규 API는 http://127.0.0.1:8000/api/health 에서 실행 중이다.
GitHub Pages는 정적 웹사이트이므로 외부 사용자의 Recorded EEG 사용에는 별도 Backend 호스팅과 VITE_BCI_API_BASE 또는 reverse proxy가 필요하다.
복원이 필요하면 백업의 RESTORE.md와 MIGRATION_MANIFEST.json에 따라 원래 경로가 비어 있는지 확인하고 함께 이동한다. 백업 파일을 신규 추론 Backend에 섞지 않는다.
