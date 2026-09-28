# 🧟 Shelter Mind — 유니티 2D BCI 카드게임 세팅 가이드

`bci_tcp_server.py` (온라인 프로토콜)와 TCP로 연동되는 유니티 2D 카드게임 클라이언트입니다.
**UI를 코드로 자동 생성**하므로 씬 조립이 거의 없습니다. 스크립트 하나만 올리면 게임이 통째로 뜹니다.

---

## 0. 준비물

- Unity Hub + Unity 에디터 (LTS 권장: **2022.3 LTS** 또는 **Unity 6000 LTS**)
- 설치 모듈: **기본 에디터만**. Android/iOS/WebGL/Visual Studio 등은 체크 해제(PC 데모용)
- (선택) 실제 BCI 연동 시 Python + `bci_tcp_server.py`

---

## 1. 프로젝트 열기

이 `unity_project` 폴더 자체가 유니티 프로젝트 루트입니다.

- **방법 A (이 폴더를 프로젝트로 사용):** Unity Hub → `Add` → `Add project from disk` → 이 `unity_project` 폴더 선택 → 열기
  - 처음 열면 유니티가 `Library/`, `ProjectSettings/` 등을 자동 생성합니다(수 분 소요).
- **방법 B (새 2D 프로젝트를 따로 만든 경우):** 새 프로젝트의 `Assets/` 안으로 이 폴더의 `Assets/Scripts` 와 `Assets/StreamingAssets` 를 통째로 복사해 넣으세요.

> ⚠️ **OneDrive 주의:** 프로젝트가 OneDrive 폴더 안에 있으면 `Library/` 캐시까지 동기화하려다 느려지거나 충돌날 수 있습니다.
> 가능하면 프로젝트를 OneDrive 밖(예: `C:\UnityProjects\ShelterMind`)에 두고, `Assets\Scripts` 와 `Assets\StreamingAssets` 만 복사하는 방식을 권장합니다.

---

## 2. 씬 세팅 (딱 2단계)

UI는 전부 코드로 생성되므로 드래그 조립이 없습니다.

1. 상단 메뉴 `File → New Scene` → **Basic 2D** (또는 Empty) 선택 후 저장 (예: `Assets/Main.unity`)
2. `Hierarchy` 창에서 우클릭 → `Create Empty` → 생성된 오브젝트 이름을 `Bootstrap` 으로
3. `Bootstrap` 선택 → Inspector에서 `Add Component` → **UIBootstrap** 검색해서 추가

끝입니다. (Canvas, EventSystem, 카메라, HUD, 카드, 엔딩 패널, BCIClient/GameManager 전부 자동 생성됩니다.)

---

## 3. 실행

에디터 상단 ▶ **Play** 버튼 클릭.

### 서버 없이 (키보드 시뮬레이션)
서버가 안 켜져 있어도 바로 플레이 가능합니다. `BCIClient` 가 자동으로 키보드 폴백으로 전환됩니다.

| 키 | 동작 |
| :-- | :-- |
| `←` 또는 `A` (꾹) | P(LEFT) 상승 → 80% 도달 시 왼손(거절/수성) 발화 |
| `→` 또는 `D` (꾹) | P(RIGHT) 상승 → 80% 도달 시 오른손(수락/공격) 발화 |
| 키 떼기 | 확률이 50% baseline 으로 감쇄 |
| `Space` | 카드 읽기 단계 스킵 |

### 실제 BCI 서버와 연동
1. 터미널에서 `python bci_tcp_server.py` 실행 (기본 `127.0.0.1:5000`)
2. 유니티 Play → `BCIClient` 가 자동 접속하여 실시간 `left_prob/right_prob/trigger` 수신
3. 서버가 꺼지면 자동으로 키보드 폴백으로 복귀, 다시 켜지면 재연결

> 서버 주소/포트를 바꾸려면 `Bootstrap` 오브젝트의 `BCIClient` 컴포넌트에서 `Host`/`Port` 를 조정하세요.

---

## 4. 온라인 프로토콜 4단계 (자동 진행)

| 단계 | 내용 | EEG |
| :-- | :-- | :-- |
| **Step 1** 카드 읽기 | 스토리/선택지 표시 (`Space`로 스킵) | OFF |
| **Step 2** 준비 | 화면 중앙 `+` 1초 | OFF |
| **Step 3** 실시간 MI | 최대 4초, 80% 도달 시 즉시 발화 / 타임아웃 시 최고 확률 방향 | ON |
| **Step 4** 피드백 & 휴식 | 카드 스와이프 + 자원 반영, 2초 휴식 | OFF |

---

## 5. 게임 규칙 요약

- 4대 자원(🍖식량 · 🔫탄약 · 🏰내구도 · 👥사기), 각 0~100 시작 50
- 어느 하나라도 **0% 또는 100%** 도달 시 파멸 엔딩(8종)
- 30일(턴) 생존 시 승리 엔딩(3종): 사기 80%↑ 대승리 / 식량·내구도 70%↑ 백신 완제 / 그 외 일반 승리
- 카드 데이터는 `Assets/StreamingAssets/cards.json` (web_app 과 동일, 20종)

---

## 6. 파일 구조

```
unity_project/
├── Assets/
│   ├── Scripts/
│   │   ├── CardData.cs      # 카드 & 서버 패킷 데이터 모델
│   │   ├── BCIClient.cs     # TCP 수신(백그라운드 스레드) + 키보드 폴백
│   │   ├── CardView.cs      # 카드 틸팅/스와이프 연출
│   │   ├── GameManager.cs   # 자원/4단계 상태머신/30일/엔딩
│   │   └── UIBootstrap.cs   # UI 전체를 코드로 자동 생성 + 컴포넌트 배선
│   └── StreamingAssets/
│       └── cards.json       # 20종 좀비 생존 카드 (web_app 과 공유)
└── README_SETUP.md
```

---

## 7. 자주 겪는 문제

- **카드가 안 뜬다 / 콘솔에 "카드 데이터를 불러오지 못했습니다":**
  `Assets/StreamingAssets/cards.json` 이 있는지 확인. 방법 B로 복사했다면 `StreamingAssets` 폴더째 넣었는지 확인.
- **이모지(👨‍✈️ 등)가 네모로 보인다:**
  유니티 기본 폰트가 이모지를 지원하지 않아서입니다. 데모엔 지장 없으며, 필요하면 이모지 지원 TMP 폰트로 교체하면 됩니다(선택).
- **서버에 연결이 안 된다:**
  `python bci_tcp_server.py` 가 실행 중인지, 포트(5000)가 방화벽에 막히지 않았는지 확인. 연결 전이라도 키보드로 플레이는 됩니다.
```
