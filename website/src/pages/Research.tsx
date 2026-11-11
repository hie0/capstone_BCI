import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { Atlas2D } from "../components/Scenes";
import { channelInfo, type ChannelMode, sourceNote } from "../data/research";
import { Pipeline } from "./Home";
import { ResultChart } from "../components/Comparison";
export default function Research() {
  const [mode, setMode] = useState<ChannelMode>("5ch");
  const [excluded, setExcluded] = useState(false);
  const [selected, setSelected] = useState("C3");
  return (
    <main className="container research-page">
      <div className="breadcrumb">RESEARCH LAB / THE STUDY</div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">MOTOR IMAGERY · EEG</span>
          <h1>
            운동 상상 EEG의
            <br />
            시공간 제약 극복을 위한 연구
          </h1>
          <p>국립부경대학교 컴퓨터·인공지능공학부 · 캡스톤디자인</p>
        </div>
        <span className="badge research">Research overview</span>
      </div>
      <section className="section research-intro">
        <span className="eyebrow">01 / BACKGROUND</span>
        <h2>더 많은 채널이 항상 더 좋은 선택일까요?</h2>
        <p>
          운동 상상 BCI는 신체의 실제 움직임 없이 운동을 상상할 때 나타나는 EEG
          패턴을 인터페이스 명령으로 연결합니다. 이 연구는 16채널 입력의
          복잡성을 줄이는 공간적 최적화와, 세션마다 달라지는 신호 분포에
          대응하는 시간적 안정화를 함께 탐색합니다.
        </p>
        <div className="problem-grid">
          <article>
            <h3>기존 16채널의 한계</h3>
            <p>
              더 많은 입력 차원은 공분산 추정의 복잡성을 높입니다. 안구·근전도
              등 비운동 영역 잡음도 함께 유입될 수 있습니다.
            </p>
          </article>
          <article>
            <h3>5~7채널 선정 근거</h3>
            <p>
              감각운동 피질 부근의 C3·Cz·C4와 전운동 관련 F3·F4를 중심으로
              구성합니다. 보조 전극의 기여는 피험자에 따라 검증되어야 합니다.
            </p>
          </article>
        </div>
      </section>
      <section className="section">
        <div className="section-title">
          <div>
            <span className="eyebrow">02 / INTERACTIVE EEG CHANNEL ATLAS</span>
            <h2>전극 하나하나의 역할을 탐색하세요.</h2>
          </div>
        </div>
        <div className="atlas-panel panel">
          <div>
            <div className="segmented wrap">
              {(["16ch", "5ch", "7ch"] as ChannelMode[]).map((m) => (
                <button
                  className={!excluded && mode === m ? "active" : ""}
                  key={m}
                  onClick={() => {
                    setMode(m);
                    setExcluded(false);
                  }}
                >
                  {m === "16ch"
                    ? "All 16Ch"
                    : m === "5ch"
                      ? "Core 5Ch"
                      : "Extended 7Ch"}
                </button>
              ))}
              <button
                className={excluded ? "active" : ""}
                onClick={() => setExcluded(true)}
              >
                Excluded Channels
              </button>
            </div>
            <Atlas2D
              mode={mode}
              selected={selected}
              onSelect={setSelected}
              excluded={excluded}
            />
          </div>
          <div>
            <span className="eyebrow">CHANNEL ANATOMY</span>
            <strong className="electrode-name">{selected}</strong>
            <h3>{channelInfo(selected)}</h3>
            <p>
              전극에 마우스를 올리거나 클릭하여 설명을 확인하세요. 배치도는
              교육용 개념도이며 개인의 정확한 해부학적 좌표를 나타내지 않습니다.
            </p>
            <p className="source-note">
              16ch 순서: 로컬 docs/00_requests.md의 전극 매핑. Core 5ch: 제공
              요청서. Extended 7ch: Core + T7/T8 미검증 콘셉트. 피험자별 연구
              프로파일은 아직 연결되지 않았습니다.
            </p>
          </div>
        </div>
      </section>
      <section className="section">
        <span className="eyebrow">03 / PROCESSING PIPELINE</span>
        <h2>신호 처리 파이프라인</h2>
        <Pipeline />
        <div className="research-intro">
          <h3>세션 간 변동과 TTA</h3>
          <p>
            Test-time adaptation은 테스트 시점의 신호 분포 차이에 대응하기 위한
            적응 과정입니다. 이 사이트는 보고된 공분산·영점 안정화의 취지를
            설명하며, 브라우저에서 모델을 학습하거나 TTA를 실행하지 않습니다.
            효과는 피험자와 평가 조건별로 확인해야 합니다.
          </p>
        </div>
      </section>
      <section className="section">
        <span className="eyebrow">04 / RESULTS & ABLATION</span>
        <h2>구성 요소에 따른 성능 변화</h2>
        <div className="panel">
          <ResultChart />
          <p className="source-note">{sourceNote}</p>
        </div>
        <div className="insight-row">
          <div>
            <span>LOSO AUC</span>
            <strong>0.8191</strong>
            <p>LOSO 교차 검증 평균</p>
          </div>
          <div>
            <span>LOSO BA</span>
            <strong>76.64%</strong>
            <p>LOSO 교차 검증 평균</p>
          </div>
          <div>
            <span>LIVE BA</span>
            <strong>54.48%</strong>
            <p>현장 라이브 · 별도 평가 조건</p>
          </div>
        </div>
        <p className="muted">
          Ablation: 16ch only 69.28% → 16ch + TTA 70.11%; Low-channel only
          72.09% → Low-channel + TTA 74.66%. 보고된 평균값의 비교이며 통계적
          유의성이나 모든 피험자에서의 개선을 의미하지 않습니다.
        </p>
      </section>
      <section className="section conclusion">
        <span className="eyebrow">05 / NEXT STEPS</span>
        <h2>연구실의 가능성을 일상의 안정성으로.</h2>
        <p>
          채널 축소와 적응의 가능성을 확인하되, 현장 라이브 성능과 사후 재분석
          사이의 차이를 해결해야 합니다. 향후 독립 세션 평가, 피험자별 채널
          검증, 실제 장비와의 연결을 통해 신뢰성을 확인할 필요가 있습니다.
        </p>
        <Link className="button primary" to="/simulation">
          인터랙티브 시뮬레이션 <ArrowUpRight size={17} />
        </Link>
      </section>
    </main>
  );
}
