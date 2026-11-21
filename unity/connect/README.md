# 🧠 Unity-BCI Connection Module (온라인 프로토콜 연동 모듈)

이 디렉토리는 **Explore 뇌파 장비 & 사전학습 머신러닝 파이프라인(`neuro_feedback3_finetuned.py`)**과 **유니티 2D 카드게임 클라이언트(`unity`)**를 TCP 소켓(`127.0.0.1:5000`)으로 안정적으로 연결하기 위한 전용 서버 및 진단 툴 모음입니다.

---

## 🏗️ 전체 연동 아키텍처

```
┌─────────────────────────────────┐        TCP Socket (Port 5000)        ┌───────────────────────────────────┐
│     Python BCI 백엔드 엔진        │ ──────────────────────────────────> │        Unity 3D/2D 프론트엔드        │
│                                 │    JSON Lines ("\n" Delimited)      │                                   │
│ 1. Explore EEG (또는 가상 뇌파)    │                                     │ 1. BCIClient.cs (백그라운드 수신)    │
│ 2. Bandpass/CAR/Filter-Bank     │  {                                  │ 2. DynamicFadingCue.cs (동적 피드백) │
│ 3. Shrinkage Covariance + CSP   │    "left_prob": 0.84,               │ 3. EEGWaveformMonitor.cs (C3/C4파형)│
│ 4. Tangent Space + SVM          │    "right_prob": 0.16,              │ 4. CardView.cs (실시간 틸트/스와이프)  │
│ 5. Dynamic Fading Tracker (L0~4)│    "trigger": "LEFT",               │ 5. GameManager.cs (4단계 상태머신)  │
│ 6. C3 / C4 실시간 전압 텔레메트리  │    "level": 4,                      │                                   │
└─────────────────────────────────┘    "c3_uV": 11.2, "c4_uV": 6.8       └───────────────────────────────────┘
                                     }
```

---

## 📂 파일 구성 및 역할

| 파일명 | 종류 | 설명 |
| :--- | :--- | :--- |
| **`bci_online_server.py`** | 핵심 서버 | `neuro_feedback3_finetuned.py`의 전처리/특징추출/SVM 모델을 헤드리스로 구동하여 유니티에 0.25초마다 실시간 스트리밍 |
| **`bci_tcp_server.py`** | 표준 진입점 | `bci_online_server.py`의 기본 엔트리포인트 (README_SETUP.md 및 BCIClient.cs 표준 호환) |
| **`dummy_bci_server.py`** | 초경량 시뮬레이터 | 외부 라이브러리(numpy, sklearn 등) 없이 표준 파이썬만으로 16초 시나리오 가상 뇌파 스트리밍 |
| **`test_connection.py`** | 진단 클라이언트 | 유니티 없이도 터미널에서 TCP 소켓 접속, 지연 시간(RTT), 패킷 규격을 1초 만에 검증 |
| **`start_mock.bat`** | 원클릭 실행 | Explore 장비 없이 **실제 ML 모델(`.joblib`) 파이프라인**으로 가상 뇌파 스트리밍 시작 |
| **`start_server.bat`** | 원클릭 실행 | 실제 **Explore EEG 블루투스 장비(`Explore_DABP`)**와 연결하여 실시간 스트리밍 시작 |
| **`start_dummy.bat`** | 원클릭 실행 | 의존성 없이 즉시 가상 BCI 서버 가동 |
| **`test_client.bat`** | 원클릭 실행 | 현재 실행 중인 BCI 서버의 패킷 정상 수신 여부 진단 |

---

## 🚀 빠른 시작 가이드 (3가지 실행 모드)

### 모드 1: 가상 뇌파 + 실제 ML 모델 파이프라인 테스트 (가장 추천 ⭐)
Explore EEG 장비가 당장 없어도, **학습된 모델 파일(`oyj_model.joblib`)과 실제 전처리/특징추출/분류기 코드 전체를 구동**하여 유니티와 연동합니다.
```bash
# 더블 클릭: start_mock.bat
# 또는 터미널 실행:
python bci_online_server.py --mock --subject oyj --model-dir ../../model
```

### 모드 2: 실제 Explore EEG 블루투스 장비 연동
피험자가 캡을 착용하고 실제 뇌파로 게임을 조작할 때 사용합니다.
```bash
# 더블 클릭: start_server.bat
# 또는 터미널 실행:
python bci_online_server.py --device Explore_DABP --subject oyj --model-dir ../../model
```

### 모드 3: 초경량 가상 서버 (라이브러리 미설치 환경)
파이썬 기본 환경만 있는 다른 조원 컴퓨터나 가벼운 노트북에서 유니티 UI만 테스트할 때 사용합니다.
```bash
# 더블 클릭: start_dummy.bat
# 또는 터미널 실행:
python dummy_bci_server.py
```

---

## 📡 전송되는 JSON 패킷 스펙 (BCIPacket)

서버는 매 `0.25초(4Hz)`마다 개행 문자(`\n`)로 구분된 단일 JSON 라인을 브로드캐스트합니다:

```json
{
  "left_prob": 0.842,
  "right_prob": 0.158,
  "trigger": "LEFT",
  "level": 4,
  "c3_uV": 11.20,
  "c4_uV": 6.85,
  "elapsed_sec": 14.25
}
```

* **`left_prob` / `right_prob`**: 좌/우 운동 상상 확률 ($0.0 \sim 1.0$)
* **`trigger`**: 발화 상태 (`"NONE"`, `"LEFT"`, `"RIGHT"`, `"NEUTRAL"`)
  * `left_prob >= 0.80` 또는 `level == 4` 시 `"LEFT"`
  * `right_prob >= 0.80` 또는 `level == 4` 시 `"RIGHT"`
  * $0.40 \sim 0.60$ 사이는 `"NEUTRAL"`
* **`level`**: Chae et al. (2012) **Dynamic Fading 단계** ($0 \sim 4$)
  * Level 0: 불확실 (원형 점선)
  * Level 1~3: 방향성 확신도 점진적 상승 (화살표 농도 증가)
  * Level 4: 트리거 확정 발화!
* **`c3_uV` / `c4_uV`**: 좌/우 운동 피질 채널의 실시간 전압 ($uV$)
  * 유니티 오실로스코프 화면(`EEGWaveformMonitor.cs`)에 실시간 파형으로 렌더링됨
* **`elapsed_sec`**: 세션 경과 시간 (초)

---

## 🧪 연동 검증 방법 (Step-by-Step)

1. `unity/connect` 폴더에서 `start_mock.bat` 실행
   * 터미널에 `[BCI TCP Server] Listening on 127.0.0.1:5000` 문구가 출력되는지 확인
2. 새 터미널 또는 `test_client.bat` 실행
   * 25개 패킷이 `250ms` 간격으로 정상 수신되는지 확인
3. Unity 에디터를 열고 상단 ▶ **Play** 버튼 클릭
   * 서버 콘솔에 `[+] Unity Connected from 127.0.0.1:...` 출력
   * 유니티 상단 헤더 상태가 녹색 연결 상태로 전환되며 카드가 뇌파 확률에 맞춰 틸트(기울기) 및 스와이프되는지 확인!
