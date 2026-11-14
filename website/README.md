# NEUROLINK · MI-BCI Interactive Research Website

국립부경대학교 컴퓨터·인공지능공학부 캡스톤 연구 소개 및 BCI 체험 프로토타입. 웹사이트 소스는 `website/`, 실제 EEG 추론 서버는 저장소 루트의 `backend/`입니다. 수동·합성 모드는 독립 실행되며 Recorded EEG 모드는 새 Backend의 REST API와 WebSocket에 연결됩니다.

## 실행

### https://hie0.github.io/capstone_BCI/

Node.js 20.19+ 또는 22.12+ 권장. 개발 시 검증한 환경은 Node 24입니다.

```sh
cd website
npm ci
npm run dev
```

http://127.0.0.1:5173 에 접속합니다. 빌드: `npm run build`, 정적 빌드 미리보기: `npm run preview`.

Recorded EEG를 사용하려면 저장소 루트에서 `backend/.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`도 실행합니다. 데이터 경로·환경·배포 설정은 [Backend 실행 안내](../backend/LOCAL_SETUP.md)를 참고하세요. 구형 연구 Backend와 모델의 백업 목록은 [전환 기록](../BACKEND_MIGRATION.md)에 있습니다.

## 구조

```
website/
├── src/
│   ├── main.tsx                  # HashRouter, 공통 헤더/푸터, 지연 로딩
│   ├── store.ts                  # Zustand 공통 설정 및 장치 상태/명령 기록
│   ├── styles.css                # 반응형 디자인, 1440/1024/390px
│   ├── data/
│   │   ├── research.ts           # 보고서 요약 수치, 전극 역할, 타입
│   │   └── replay.ts             # ReplaySource/EEGFrame/PredictionRecord 어댑터 경계
│   ├── components/
│   │   ├── Scenes.tsx            # 3D 거실, 두부/전극, 2D 오류 대체 화면
│   │   ├── SmartHome.tsx         # 메뉴 대기 확정, 네 장치, 명령 모니터
│   │   ├── Wearable.tsx          # 전극 구성, MI 설명, 디바이스 비교
│   │   ├── Controls.tsx          # 공유 설정, 합성 파형
│   │   ├── Comparison.tsx        # Recharts 연구 결과 비교
│   │   └── Replay.tsx            # 합성 리플레이/타임라인
│   └── pages/                   # Home, Research, Simulation
├── tests/experience.spec.ts      # 주요 사용 흐름 및 WebGL fallback 테스트
├── tests/artifacts/              # 테스트 화면 캡처
└── ../.github/workflows/pages.yml # 저장소 루트의 배포 워크플로
```

## 페이지 및 조작

- `/#/`: 연구 소개, 3D 개념 두부와 전극, 핵심 결과, 채널 최적화, 파이프라인, 응용 진입.
- `/#/research`: 배경, 16ch 한계, 클릭/키보드 전극 Atlas, 선정 근거, TTA, 결과 및 Ablation, 한계/향후 연구.
- `/#/simulation`: 기본 BCI Applications, Model Comparison, EEG Replay.
- **Smart Home**: LEFT/L, RIGHT/R로 4개 메뉴 순환. 마지막 탐색 입력 후 2초 대기하면 제어 모드 진입. 메뉴 카드를 클릭해도 동일하게 대기 선택. LEFT/RIGHT로 조명, 커튼, 온도(16~30°C), TV(1~5 순환)를 조작. UI 돌아가기로 탐색 복귀. Reset은 장치/명령/자동재생을 초기화하고 실험 설정은 유지.
- **Simulated EEG**: Input mode를 변경 후 시작/정지. 난수 방향과 합성 confidence를 전달하며 실제 모델 성능을 흉내 내지 않음. 탭/응용 전환 시 자동 입력 정지.
- **Wearable**: 16/5/7ch 전환, 전극 클릭, 2D/3D 전환, LEFT/RIGHT MI 대측성 설명. 공유 채널·TTA·모델·피험자·세션·속도는 화면 이동 시 유지(새로고침하면 초기화). 디바이스는 미제작·미검증 콘셉트.
- **Comparison**: 보고된 사후 재분석 BA 네 조건 표시. 현재 채널 그룹/TTA의 막대 강조. LOSO·현장 라이브·BA/AUC 선택 지원; 미제공 조건은 명시적으로 표시.
- **Replay**: Recorded EEG 또는 합성 입력의 파형·예측, 재생/일시정지/리셋/속도/채널/타임라인 탐색. 탭을 나가면 재생 종료.
- 모든 3D 씬은 드래그 회전, WebGL 미지원/렌더 오류 시 2D 대체 화면 제공. 외부 모델 파일 다운로드 불필요.

## 데이터 신뢰성과 미연결 기능

1. **Research Data**: 사용자 제공 개발 요청서의 보고서 요약값을 그대로 수록. LOSO AUC 0.8191 / BA 76.64%, 온라인 50세션 사후 재분석 BA 69.28/70.11/72.09/74.66%, 현장 라이브 BA 54.48%. 이 구현에서 재계산·재현 검증한 값은 아님. 평가 조건과 출처를 카드 tooltip·차트 설명에 표시.
2. **Synthetic Demo**: 합성 파형·데모 피험자/세션·예측·confidence. 수동 입력에는 confidence를 생성하지 않음. 참 라벨은 null. 모델·TTA 선택은 상태 공유/연구 비교용이며 합성 정확도에 영향을 주지 않음.
3. **Application Simulation**: 가상 장치 상태 변화 및 교육용 두부/반구 표시. 실제 장치/실시간 뇌 활성화 아님.
4. 16ch 매핑은 원본 로컬 연구 폴더의 `docs/00_requests.md` (이 저장소에는 미포함)와 일치. Core 5ch는 요청서의 F3/F4/C3/Cz/C4. 기존 로컬 모델 인벤토리의 일부 구성은 요청서와 다름. **연구용 Extended 7은 Core+P7/P8이다**. Recorded EEG는 신규 Backend가 반환한 실제 active_channels를 사용하며 해당 추론 montage와 역사적 연구용 구성을 구분한다.
5. 5ch/7ch 개별·피험자별 수치, 온라인 AUC, 통계적 유의성, 착용시간·가격·배터리 수명은 임의로 생성하지 않음.
6. Recorded EEG는 새 Backend의 실제 joblib과 12개 로컬 EEG 세션에 연결됩니다. 세션별 Calib20 추론의 실제 montage·활성 채널·모델 출력을 표시하고, 연결 실패를 합성 데이터로 대체하지 않습니다. 품질 기준 미달 시 장치 명령을 보류합니다. 실제 장비 수집 및 재활 손 피드백은 이번 범위에 포함하지 않습니다.

## 브라우저 검증

개발 서버 실행 후 `npm test`. 기본 설정은 로컬 설치 Google Chrome (`channel: 'chrome'`) 사용. Chrome이 없는 환경은 Playwright 지원 OS에서 `npx playwright install chromium` 후 `playwright.config.ts`의 channel을 제거합니다. Mac 13은 현재 Playwright Chromium 다운로드 미지원이므로 설치된 Chrome을 이용합니다.

테스트 범위: 메뉴 양방향 이동·대기 확정, 네 장치 제어, 로그/Reset, 자동 입력 정지, 공유 설정, 누락된 성능값 표시, Replay, 1440px/1024px/390px, WebGL 불가 대체 UI. 스크린샷은 `tests/artifacts`에 기록됩니다.

## GitHub Pages 배포

HashRouter와 Vite `base: './'`를 사용하므로 저장소 서브경로에서도 새로고침/자산 경로가 유지됩니다.

GitHub Pages는 정적 프론트엔드만 배포합니다. Recorded EEG에는 별도로 접근 가능한 Backend가 필요하며, 빌드 시 `VITE_BCI_API_BASE` 또는 `/api`·`/ws` reverse proxy를 설정해야 합니다. 원본 EEG와 Backend 가상환경은 Pages 배포물에 포함하지 않습니다.

저장소 루트 `.github/workflows/pages.yml`이 `website/`에서 의존성 설치와 빌드를 수행하고 **website/dist만** 배포합니다.

1. GitHub 저장소 Settings → Pages → Build and deployment → Source를 **GitHub Actions**로 설정합니다.
2. game 브랜치에 웹사이트 변경을 push하거나 Actions → Deploy NEUROLINK to GitHub Pages → Run workflow에서 game을 선택해 실행합니다.
3. 배포 성공 후 Pages에 표시되는 주소로 접속합니다. 예상 주소: `https://hie0.github.io/capstone_BCI/` (배포 전에는 접속되지 않을 수 있음).

루트의 기존 Python 모델과 Unity 프로젝트는 사이트 빌드에 포함하지 않습니다. `node_modules`, 연구 데이터, 모델 파일을 사이트 배포물에 복사하지 않습니다.

소스 서식 정리: `npm run format`. 3D 엔진 번들 약 719kB(압축 전)에 대한 Vite 크기 경고가 있으나 빌드 오류는 아닙니다. 차트와 3D 엔진은 별도 번들로 분리됩니다.

## 최종 검증 결과

- `npm run build`: TypeScript 검사 및 Vite 프로덕션 빌드 성공.
- `npm test`: Chrome 브라우저 시나리오 8개 모두 통과.
- 1440px 데스크톱, 1024px 태블릿, 390px 모바일 화면 확인.
- 장치 네 가지의 제어, 메뉴 대기 확정, 로그·리셋, 자동 입력 시작/정지 및 2배속, 5/7/16ch 전환, 3D 전극 선택, 모델·TTA·채널 설정 공유, 연구값 누락 처리, 리플레이 및 WebGL 불가 대체 UI 검증.
- 화면 캡처: `tests/artifacts/smart-home-1440.png`, `wearable-3d-1440.png`, `wearable-1440.png`, `home-1440.png`, `tablet-1024.png`, `mobile-390.png`.
- Recorded EEG 실행에는 개발 서버와 Backend를 함께 실행하세요. 자세한 명령은 위 실행 안내를 참고하세요.
