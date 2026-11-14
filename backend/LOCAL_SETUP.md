# 현재 웹사이트용 Backend 실행

저장소 루트의 `backend/`만 서버로 사용한다. 기존 연구용 `website/backend/`나 재현 모델을 Python 경로에 추가하지 않는다.

```bash
cd /Users/kimhieyoung/Desktop/capstone_data/WEB/capstone_BCI
backend/.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

이 컴퓨터의 데이터 루트는 git에서 제외한 `backend/local_cache/data_root.txt`에 설정했다.
실제 구조는 `website/capstone_core_handover/online/{WMJ,KGE,OYJ,KHY}/{participant}_online{session}/`다.
다른 컴퓨터에서는 서버 실행 전에 `BCI_DATA_ROOT`를 해당 `online/` 폴더의 절대 경로로 지정한다.
환경변수가 hint 파일보다 우선하며, 경로를 변경하면 서버를 재시작한다.

새 로더는 ExG·Marker·Meta·Calibration·Online 로그를 직접 읽는다. 옛 Python, 모델, 연구 CSV나 별도 pickle EEG 캐시는 필요하지 않다.
250Hz/uV, 16개 채널, calibration LEFT10/RIGHT10, Marker12/13/33 정렬, 2초 MI 구간과 로그 순서를 검증한다.
모델 export 당시와 일치하는 log sample index를 사용하며 Marker와의 차이도 확인한다.
로컬 원본 EEG는 12세션/540 online trials/240 calibration trials이며, 모델 카탈로그의 79세션과 구분한다.

```bash
cd website
npm run dev
```

- 웹사이트: http://127.0.0.1:5173/#/simulation
- API 상태: http://127.0.0.1:8000/api/health
- API 문서: http://127.0.0.1:8000/docs
- `Input mode → Recorded EEG` 선택 후 재생한다. Session·Participant·채널·TTA를 바꾸면 재생 상태가 초기화된다.
- 실제 모델 응답으로 파형과 명령을 표시한다. 품질 기준 미달이면 가상 장치 명령을 보내지 않는다.
- 웹소켓 연결별 TTA 상태를 분리하고 종료 시 정리한다. 일시정지 후에는 기록 위치까지 인과적으로 복원한다.
- 서버 연결 실패를 명시적으로 표시하며 합성 데이터로 대체하지 않는다.

개발 서버는 `/api` 및 `/ws`를 8000 포트로 프록시한다. 정적 웹사이트 배포에서는 동일 경로의 reverse proxy 또는 `VITE_BCI_API_BASE=https://실제-API-호스트`를 설정해야 한다.
새 Backend의 세션별 Calib20 추론은 Reg-CSP+sLDA다. 연구 페이지에 설명된 기존 모델명으로 응답을 가장하지 않고 실제 montage와 활성 전극을 표시한다.
사전 export 모델의 세션 선택 및 품질 임계값에 대한 연구상 해석은 원본 연구 프로토콜과 구분해야 한다. 이번 검증은 서버·데이터·웹사이트 연결 검증이다.

모델은 재학습·재저장하지 않았다. 실제 설치 환경은 `requirements-lock.txt`에 기록했으며 모델의 sklearn1.9.1 버전과 일치한다.
새 환경이 필요하면 `python3 -m venv backend/.venv` 후 해당 환경에서 `pip install -r backend/requirements-lock.txt`를 실행한다.

```bash
backend/.venv/bin/python backend/validate_local_integration.py
cd website
npx playwright test tests/recorded.spec.ts
npm run build
```

검증 근거와 스크린샷은 git에서 제외한 `backend/local_cache/migration/`에 있다. 원본 EEG·개인 경로·가상환경·캐시를 저장소에 추가하지 않는다.


Phase4에서는 Smart Home과 Wearable 양쪽에서 Participant/Session·16ch/Low Channel·TTA·속도를 설정할 수 있다. Decision score=P(RIGHT), logit, latency, Quality Gate 및 관측 trial Accuracy/BA는 실제 응답으로 표시한다.
`Low Channel`은 제공된 joblib의 low 키를 그대로 사용한다. TTA ON/OFF 사이 montage가 다를 수 있으므로 고정 모델 TTA 단독 비교로 해석하지 않는다. 상세 조건과 검증 결과는 [PHASE4_INTEGRATION_RESULTS.md](../PHASE4_INTEGRATION_RESULTS.md)에 있다.

Backend는 BLAS 계열 스레드를 프로세스당 1개로 제한하고, 독립 EEG 세션은 최대 2개 동시 로딩한다. 세션별 모델과 EEG는 서버 메모리 캐시를 재사용한다. 추가 Low 검증만 실행하려면 저장소 루트에서 `backend/.venv/bin/python backend/validate_phase4.py`를 실행한다(2개 검증 프로세스, 새 학습 없음). 로그/결과는 `backend/local_cache/phase4/`에 저장한다.
