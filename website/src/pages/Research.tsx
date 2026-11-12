import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { Atlas2D } from "../components/Scenes";
import { channelInfo, type ChannelMode, sourceNote } from "../data/research";
import { Pipeline } from "./Home";
import { ResultChart, SubjectResultChart } from "../components/Comparison";
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
            감각운동 저채널 EEG의
            <br />
            실용화를 위한 안정화 연구
          </h1>
          <p>국립부경대학교 컴퓨터·인공지능공학부 · 캡스톤디자인</p>
        </div>
        <span className="badge research">Research overview</span>
      </div>
      <section
        id="research-content"
        className="section research-intro scroll-section"
      >
        <span className="eyebrow">01 / BACKGROUND</span>
        <h2>더 많은 채널이 항상 더 좋은 선택일까요?</h2>
        <p>
          4인 피험자의 오프라인 3,009 트라이얼과 온라인 50세션 3,910회를
          분석했습니다. 16채널의 비운동 잡음을 물리적으로 격리하고, 5~7채널
          공분산 안정화와 실시간 영점 정렬을 결합했습니다.
        </p>
        <div className="problem-grid">
          <article>
            <h3>기존 16채널의 한계</h3>
            <p>
              공분산 조건수 74.80, 비운동 채널 CSP 에너지 누설 38.9%, 전두부
              안구 잡음 32.7%가 타 날짜 일반화를 방해했습니다.
            </p>
          </article>
          <article>
            <h3>5~7채널 선정 근거</h3>
            <p>
              C3·Cz·C4와 F3·F4를 중심으로 전극을 68.8%, 공분산 모수를 136개에서
              15개로 89% 줄이고 착용 시간을 15분에서 3분으로 단축했습니다.
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
              Core 5ch는 F3·F4·C3·Cz·C4입니다. 발표자료의 피험자별 최적 구성은
              WMJ·KHY 7ch, KGE·OYJ 5ch이며 7ch 보조 채널은 모델별 검증 구성을
              나타냅니다.
            </p>
          </div>
        </div>
      </section>
      <section id="research-process" className="section scroll-section">
        <span className="eyebrow">03 / PROCESSING PIPELINE</span>
        <h2>신호 처리 파이프라인</h2>
        <Pipeline />
        <div className="research-intro">
          <h3>세션 간 변동과 TTA</h3>
          <p>
            ① 5~7ch 물리 격리 ② OAS 수축 공분산과 리만 접공간 추정 ③
            CausalEA·CausalLogitCenter 기반 무감독 온라인 영점 정렬의
            3단계입니다. 16ch 조건수 74.80은 5ch에서 14.20, OAS 결합 후 8.16으로
            안정화됐습니다.
          </p>
        </div>
      </section>
      <section id="research-results" className="section scroll-section">
        <span className="eyebrow">04 / RESULTS & ABLATION</span>
        <h2>구성 요소에 따른 성능 변화</h2>
        <div className="panel">
          <ResultChart />
          <p className="source-note">{sourceNote}</p>
        </div>
        <div className="panel subject-comparison-panel">
          <div className="panel-title">
            피험자별 LOSO 성능{" "}
            <span className="badge research">16ch vs 5~7ch</span>
          </div>
          <SubjectResultChart />
        </div>
        <div className="insight-row">
          <div>
            <span>LOSO AUC</span>
            <strong>0.8100</strong>
            <p>4인 LOSO 제안 모델 평균</p>
          </div>
          <div>
            <span>LOSO BA</span>
            <strong>76.06%</strong>
            <p>18개 런 · 1,440회</p>
          </div>
          <div>
            <span>ONLINE 50 SESSIONS</span>
            <strong>74.71%</strong>
            <p>영점조절 적용 · 3,910회</p>
          </div>
        </div>
        <p className="muted">
          저채널 물리 격리는 +10.5%p, 실시간 영점조절은 +12.3%p의 독립 기여를
          보였으며 결합 후 온라인 BA가 54.50%에서 74.71%로 +20.21%p
          향상됐습니다(p &lt; 10⁻¹⁷).
        </p>
      </section>
      <section className="section conclusion">
        <span className="eyebrow">05 / NEXT STEPS</span>
        <h2>연구실의 가능성을 일상의 안정성으로.</h2>
        <p>
          전극 56~69% 감축, 연산 92~97% 절감, LOSO 4전 4승을 확인했습니다. 다음
          단계는 5~7전극 헤드밴드와 1~2분 고속 영점 보정을 실제 웨어러블
          환경에서 검증하는 것입니다.
        </p>
        <Link className="button primary" to="/simulation">
          인터랙티브 시뮬레이션 <ArrowUpRight size={17} />
        </Link>
      </section>
    </main>
  );
}
