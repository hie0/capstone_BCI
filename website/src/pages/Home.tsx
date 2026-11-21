import { useEffect, useState } from "react";
import {
  channelInfo,
  core,
  electrodeNames,
  positions,
  type ChannelMode,
  type Direction,
} from "../data/research";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  BrainCircuit,
  Layers,
  Waves,
  Scan,
  ShieldCheck,
  House,
  Gamepad2,
  MessageSquareText,
} from "lucide-react";
import { Scene, Atlas2D, activeChannels } from "../components/Scenes";
import { HeroBust } from "../components/HeroBust";
import { StabilityDiagram } from "../components/StabilityDiagram";
import { StabilityFormula } from "../components/StabilityFormula";
import { ResultChart, SubjectResultChart } from "../components/Comparison";
import { losoF1Average, onlineF1Average, externalMacroF1 } from "../data/researchBenchmarks";
export function Pipeline() {
  const steps = [
    {
      icon: Waves,
      title: "EEG 직접 측정",
      desc: "4인 피험자 · 오프라인 3,009회 · 온라인 50세션 데이터 구축",
    },
    {
      icon: ShieldCheck,
      title: "전처리",
      desc: "ArtGate90으로 이상 신호와 비운동 잡음 제거",
    },
    {
      icon: Layers,
      title: "저채널화·안정화",
      desc: "핵심 5~7채널 선택 · OAS 공분산 안정화",
    },
    {
      icon: BrainCircuit,
      title: "모델링",
      desc: "CSP·Riemannian Tangent Space 기반 특징과 개인별 분류 모델 구성",
    },
    {
      icon: Scan,
      title: "성능 검증",
      desc: "피험자·날짜 LOSO와 실전 온라인 검증",
    },
  ];
  return (
    <div className="pipeline research-workflow" aria-label="연구 수행 파이프라인">
      {steps.map((step, i) => (
        <div className="pipeline-step" key={step.title}>
          <span className="mono">0{i + 1}</span>
          <step.icon size={24} aria-hidden="true" />
          <strong>{step.title}</strong>
          <small>{step.desc}</small>
        </div>
      ))}
    </div>
  );
}

function StabilityVisual() {
  return (
    <div className="stability-visual" role="group" aria-label="BCI 신호 정렬 파이프라인">
      <div className="stability-visual-step">
        <StabilityDiagram kind="covariance" />
        <span>Cross-session Covariance</span>
      </div>
      <b aria-hidden="true">→</b>
      <div className="stability-visual-step">
        <StabilityDiagram kind="shrinkage" />
        <span>OAS Shrinkage</span>
      </div>
      <b aria-hidden="true">→</b>
      <div className="stability-visual-step">
        <StabilityDiagram kind="tangent" />
        <span>Riemannian Tangent Space</span>
      </div>
      <b aria-hidden="true">→</b>
      <div className="stability-visual-step">
        <StabilityDiagram kind="centering" />
        <span>CausalEA · CausalLogitCenter</span>
      </div>
    </div>
  );
}

function ChannelReductionGraphic() {
  return (
      <svg
        className="channel-reduction-graphic"
        viewBox="0 0 400 260"
        role="img"
        aria-label="16채널에서 핵심 5채널만 남는 애니메이션"
      >
        <ellipse cx="200" cy="133" rx="118" ry="112" />
        <path d="M184 22 L200 6 L216 22 M83 112 Q58 133 83 154 M317 112 Q342 133 317 154" />
        {electrodeNames.map((name) => {
          const [x, y] = positions[name];
          const retained = core.includes(name);
          return (
            <g
              key={name}
              className={retained ? "retained-channel" : "removed-channel"}
            >
              <circle cx={200 + x * 112} cy={133 + y * 108} r="9" />
              <text x={200 + x * 112} y={133 + y * 108 + 23}>
                {name}
              </text>
            </g>
          );
        })}
      </svg>
  );
}
export default function Home() {
  const [selected, setSelected] = useState("C4");
  const [mode, setMode] = useState<ChannelMode>("5ch");
  const [excluded, setExcluded] = useState(false);
  const [direction, setDirection] = useState<Direction | undefined>();

  useEffect(() => {
    if (!direction) return;
    const timer = window.setTimeout(() => setDirection(undefined), 5000);
    return () => window.clearTimeout(timer);
  }, [direction]);
  return (
    <main>
      <section id="research-overview" className="container hero scroll-section">
        <div className="hero-copy">
          <div className="eyebrow">
            <i className="status-dot" /> PUKYONG NATIONAL UNIVERSITY · MI-BCI
            LAB
          </div>
          <h1>
            더 적은 전극으로,
            <br />더 안정적인
            <br />
            <span className="gradient-text">뇌파 제어.</span>
          </h1>
          <div className="hero-english">Fewer Electrodes, More Stable BCI</div>
          <p>
            4인 피험자 · 오프라인 3,009회 · 온라인 50세션 전수 실증
            <br className="desktop" /> 감각운동 중심 5~7채널 최적화와
            <br className="desktop" /> 공분산·실시간 영점 안정화를 검증했습니다.
          </p>
          <div className="hero-actions">
            <Link className="button primary" to="/simulation">
              시뮬레이션 체험하기 <ArrowUpRight size={18} />
            </Link>
            <Link className="button" to="/#research-content">
              연구 자세히 보기 <ArrowRight size={17} />
            </Link>
          </div>
          <div className="hero-caption">
            <span>CAPSTONE DESIGN</span>
            <span>COMPUTER & ARTIFICIAL INTELLIGENCE</span>
          </div>
        </div>
        <div className="hero-visual">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="brain-hero">
            <Scene
              fallback={
                <Atlas2D
                  mode="5ch"
                  selected={selected}
                  onSelect={setSelected}
                />
              }
            >
              <HeroBust selected={selected} onSelect={setSelected} />
            </Scene>
          </div>
        </div>
      </section>
      <section className="container metrics">
        {[
          ["16 → 5 ~ 7", "Electrode Reduction", "최대 68.75% 전극 감소"],
          [`${losoF1Average.lowTta.toFixed(2)}%`, "LOSO Macro-F1", "타 날짜 일반화 성능"],
          [`${onlineF1Average.lowTta.toFixed(2)}%`, "Online Macro-F1", "실전 온라인 50세션"],
          [`${externalMacroF1[3].mean.toFixed(2)}%`, "External Validation", "PhysioNet 100명 검증"],
        ].map(([v, l, d]) => (
          <div
            key={l}
            tabIndex={0}
            title={`Historical research benchmark · ${l} · ${d}`}
          >
            <span>{l}</span>
            <strong>{v}</strong>
            <small>{d} ⓘ</small>
          </div>
        ))}
      </section>
      <section
        className="container research-process-overview scroll-section"
      >
        <div className="workflow-heading">
          <div>
            <span>연구 수행 과정</span>
            <strong>직접 측정한 EEG가 연구 결과가 되기까지</strong>
          </div>
          <b>직접 측정 데이터</b>
        </div>
        <Pipeline />
      </section>
      <section
        id="research-content"
        className="container section scroll-section"
      >
        <div className="section-title">
          <div>
            <span className="eyebrow">01 / 연구 내용</span>
            <h2>
              다채널 장비는 복잡하고,
              <br />
              뇌파는 날짜마다 달라집니다.
            </h2>
          </div>
          <p>
            오늘 잘 맞던 분류 모델도 다른 날짜에는 성능이 달라질 수 있습니다.
            <br />
            많은 전극과 날짜별 신호 변화가 일상적인 BCI 사용을 어렵게 합니다.
          </p>
        </div>
        <div className="problem-grid">
          <article>
            <span className="outline-number">01</span>
            <span className="problem-label">공간적 제약</span>
            <h3>16채널 구성은 착용과 준비가 복잡합니다.</h3>
            <div className="problem-visual channel-burden">
              <ChannelReductionGraphic />
              <div className="problem-visual-copy">
                <strong>16채널 구성</strong>
                <span>필요한 영역을 찾기 전, 모든 전극이 활성화됩니다.</span>
              </div>
            </div>
            <p>
              채널이 많을수록 착용 구조와 준비 과정이 복잡해지고,
              움직임·근전도·접촉 상태의 영향을 받을 경로도 늘어납니다.
            </p>
            <Link to="/#channel-method">
              제안 방법 살펴보기 <ArrowUpRight size={16} />
            </Link>
          </article>
          <article>
            <span className="outline-number">02</span>
            <span className="problem-label">시간적 변동</span>
            <h3>같은 모델도 다음 날에는 달라집니다.</h3>
            <div className="problem-visual session-drift" aria-hidden="true">
              <div>
                <span>오늘의 뇌파</span>
                <svg viewBox="0 0 120 52">
                  <path className="decision-line" d="M2 26 H118" />
                  <path className="today-wave" d="M2 35 C14 16 22 15 34 32 S54 47 66 25 S88 12 98 30 S110 42 118 24" />
                </svg>
              </div>
              <b><small>같은 모델</small>→</b>
              <div>
                <span>다음 날의 뇌파</span>
                <svg className="tomorrow-wave" viewBox="0 0 120 52">
                  <path className="decision-line" d="M2 26 H118" />
                  <g className="tomorrow-after">
                    <path
                      className="rapid-wave rapid-wave-one"
                      d="M2 27 Q6 7 10 27 T18 27 T26 27 T34 27 T42 27 T50 27 T58 27 T66 27 T74 27 T82 27 T90 27 T98 27 T106 27 T114 27 T118 20"
                    />
                    <path
                      className="rapid-wave rapid-wave-two"
                      d="M2 20 Q6 45 10 20 T18 20 T26 20 T34 20 T42 20 T50 20 T58 20 T66 20 T74 20 T82 20 T90 20 T98 20 T106 20 T114 20 T118 31"
                    />
                    <path
                      className="rapid-wave rapid-wave-three"
                      d="M2 30 Q5 4 9 30 T16 30 T23 30 T30 30 T37 30 T44 30 T51 30 T58 30 T65 30 T72 30 T79 30 T86 30 T93 30 T100 30 T107 30 T114 30 T118 13"
                    />
                  </g>
                </svg>
              </div>
              <em>신호 분포 이동 → 분류 기준 불일치</em>
            </div>
            <p>
              같은 사람·같은 동작이어도 날짜가 바뀌면 EEG의 중심과 분포가
              이동해, 어제 학습한 기준이 오늘 신호와 어긋날 수 있습니다.
            </p>
            <Link to="/#processing-method">
              안정화 과정 살펴보기 <ArrowUpRight size={16} />
            </Link>
          </article>
        </div>
      </section>
      <section id="channel-method" className="container section scroll-section">
        <div className="section-title">
          <div>
            <span className="eyebrow">02 / 제안 방법 · 핵심 채널</span>
            <h2>필요한 신호에 집중합니다.</h2>
          </div>
          <p>
            감각운동 영역을 중심으로 5~7채널을 선택해 착용 부담과 입력
            복잡도를 함께 낮췄습니다.
          </p>
        </div>
        <div className="atlas-panel panel">
          <div className="reduction-hero">
            <span>핵심 채널 축소</span>
            <strong>16 → 5~7채널</strong>
            <b>5채널 기준 68.75% 감소</b>
            <small>7채널 구성은 56.25% 감소</small>
          </div>
          <div className="atlas-explorer">
            <div className="segmented wrap">
              {(["16ch", "5ch", "7ch"] as ChannelMode[]).map((m) => (
                <button
                  className={!excluded && mode === m ? "active" : ""}
                  key={m}
                  onClick={() => {
                    setMode(m);
                    setExcluded(false);
                    setSelected(m === "5ch" ? "Cz" : m === "7ch" ? "P7" : "C4");
                  }}
                >
                  {m === "16ch"
                    ? "전체 16채널"
                    : m === "5ch"
                      ? "핵심 5채널"
                      : "확장 7채널"}
                </button>
              ))}
              <button
                className={excluded ? "active" : ""}
                onClick={() => {
                  setExcluded(true);
                  setSelected("Fp1");
                }}
              >
                제외 채널
              </button>
            </div>
            <Atlas2D
              mode={mode}
              selected={selected}
              onSelect={setSelected}
              excluded={excluded}
              direction={direction}
            />
          </div>
          <div className="atlas-insight">
            <div className="electrode-role-card channel-details-card" aria-live="polite">
              <span className="channel-card-title">◉ &nbsp;전극 상세</span>
              <strong className="electrode-name">{selected}</strong>
              <span className="channel-status-badge">
                {excluded || !activeChannels(mode).includes(selected)
                  ? "제외 전극"
                  : "활성 전극"}
              </span>
              <h3>해부학적 위치와 역할</h3>
              <p className="channel-role-copy">{channelInfo(selected)}</p>
              <h3>선정과 잡음</h3>
              <p className="channel-role-copy">
                핵심 구성은 감각운동 정보를 유지하면서 입력 차원을 줄이는 데
                초점을 둡니다. 모든 전극은 접촉 상태와 움직임에 따른 잡음의
                영향을 받을 수 있습니다.
              </p>
              <div className="motor-imagery-control">
                <strong>운동 상상</strong>
                <div className="segmented">
                  <button
                    className={direction === "LEFT" ? "active" : ""}
                    onClick={() => {
                      setDirection("LEFT");
                      setSelected("C4");
                    }}
                  >
                    왼손 상상
                  </button>
                  <button
                    className={direction === "RIGHT" ? "active" : ""}
                    onClick={() => {
                      setDirection("RIGHT");
                      setSelected("C3");
                    }}
                  >
                    오른손 상상
                  </button>
                </div>
                <p>
                  {direction === "LEFT"
                    ? "왼손 상상 → 오른쪽 감각운동 영역(C4) 강조"
                    : direction === "RIGHT"
                      ? "오른손 상상 → 왼쪽 감각운동 영역(C3) 강조"
                      : "버튼을 누르면 대응하는 감각운동 영역을 5초간 강조합니다."}
                  <br />대측성 관계를 보여주는 교육용 표현입니다.
                </p>
              </div>
            </div>
            <p>
              전극을 클릭하거나 Tab 키로 이동한 뒤 Enter를 눌러 역할을
              확인하세요. 배치도는 교육용 개념도입니다.
            </p>
          </div>
        </div>
      </section>
      <section
        id="processing-method"
        className="container section scroll-section"
      >
        <div className="section-title">
          <div>
            <span className="eyebrow">03 / 제안 방법 · 안정화</span>
            <h2>
              직접 측정한 EEG를,
              <br />날짜가 달라도 안정적인 특징으로 바꿉니다.
            </h2>
          </div>
          <p>
            측정·수집부터 전처리, 모델링, 검증까지 직접 수행하고
            <br />공분산과 분류 출력의 중심을 단계적으로 안정화했습니다.
          </p>
        </div>
        <div className="stability-method">
          <div className="stability-heading">
            <div>
              <span className="eyebrow">STABILITY CORE</span>
              <h3>안정화는 이렇게 진행했습니다.</h3>
            </div>
            <p>
              Low-channel covariance를 안정적으로 추정한 뒤, geometric features를 만들고
              온라인 신호와 classifier output의 기준점을 순차적으로 정렬합니다.
            </p>
          </div>
          <StabilityVisual />
          <div className="stability-flow">
            <article>
              <span>01 · Covariance Stabilization</span>
              <strong>OAS Shrinkage</strong>
              <StabilityDiagram kind="oas-detail" />
              <p>Shrinkage regularization으로 low-channel covariance 추정의 수치적 불안정을 완화합니다.</p>
              <code><StabilityFormula kind="oas" /></code>
            </article>
            <i aria-hidden="true">→</i>
            <article>
              <span>02 · Feature Extraction</span>
              <strong>CSP · Riemannian Tangent Space</strong>
              <StabilityDiagram kind="features" />
              <p>CSP의 variance 차이와 SPD covariance의 tangent-space vector로 LEFT/RIGHT 분류 특징을 만듭니다.</p>
              <code><StabilityFormula kind="tangent" /></code>
            </article>
            <i aria-hidden="true">→</i>
            <article>
              <span>03 · Input Alignment</span>
              <strong>CausalEA</strong>
              <StabilityDiagram kind="alignment" />
              <p>현재까지의 EEG covariance reference를 온라인으로 갱신해 신호를 정렬합니다.</p>
              <code><StabilityFormula kind="alignment" /></code>
            </article>
            <i aria-hidden="true">→</i>
            <article>
              <span>04 · Logit Centering</span>
              <strong>CausalLogitCenter</strong>
              <StabilityDiagram kind="centering" />
              <p>Classifier output의 logit bias를 보정해 session별 decision boundary shift에 대응합니다.</p>
              <code><StabilityFormula kind="centering" /></code>
            </article>
          </div>
          <div className="stability-summary">
            <span>Covariance Stabilization</span>
            <b>+</b>
            <span>Online Input Alignment</span>
            <b>+</b>
            <span>Logit Centering</span>
            <strong>→ LEFT / RIGHT MI Classification</strong>
          </div>
        </div>
      </section>
      <section
        id="research-results"
        className="container section findings scroll-section"
      >
        <div>
          <span className="eyebrow">04 / 연구 결과</span>
          <h2>
            실전 온라인 Macro-F1.
          </h2>
          <div className="result-highlight">
            <span>4인 평균 Macro-F1 · 16ch Baseline 대비</span>
            <div>
              <strong>67.46%</strong>
              <i>→</i>
              <strong>74.23%</strong>
            </div>
            <b>+6.77%p</b>
          </div>
          <p className="result-explanation">
            실전 온라인 50세션에서 16ch Baseline과 Low Channel + TTA를 비교했습니다.
            4인 전원 Macro-F1이 향상했으며, 4인 평균 개선 폭은 <b>+6.77%p</b>입니다.
          </p>
        </div>
        <div className="panel">
          <div className="panel-title">
            Online 50-session Performance — Macro-F1{" "}
            <span className="badge research">Research Data</span>
          </div>
          <ResultChart />
        </div>
      </section>
      <section className="container section research-results-detail">
        <div className="panel subject-comparison-panel">
          <div className="panel-title">
            피험자별 LOSO 성능{" "}
            <span className="badge research">16ch vs 5~7ch</span>
          </div>
          <SubjectResultChart />
        </div>
        <div className="insight-row">
          <div><span>LOSO Macro-F1</span><strong>71.72%</strong><p>+8.47%p 향상</p></div>
          <div><span>Online Macro-F1</span><strong>74.23%</strong><p>+6.77%p 향상</p></div>
          <div><span>External Macro-F1</span><strong>65.77%</strong><p>+6.44%p 향상</p></div>
          <div><span>External Improvement</span><strong>74/100</strong><p>성능 향상 피험자 수</p></div>
        </div>
        <p className="muted">
          LOSO, 온라인 50세션, PhysioNet EEGBCI 100명 검증은 별도 평가입니다.
          이 값은 historical research benchmark이며 실제 웹사이트 Backend의 동적 추론 결과와 구분합니다.
        </p>
      </section>
      <section className="container section">
        <div className="section-title">
          <div>
            <span className="eyebrow">05 / BEYOND THE LAB</span>
            <h2>연구의 다음 장면을 경험하세요.</h2>
          </div>
          <Link to="/simulation" className="text-button">
            Open interactive lab <ArrowUpRight size={17} />
          </Link>
        </div>
        <div className="application-preview">
          <Link to="/simulation?tab=applications&app=home">
            <House size={40} />
            <span>APPLICATION 01</span>
            <h3>SMART HOME 제어</h3>
            <p>LEFT와 RIGHT 명령으로 일상 기기를 제어합니다.</p>
            <ArrowUpRight />
          </Link>
          <Link to="/simulation?tab=applications&app=game">
            <Gamepad2 size={40} />
            <span>APPLICATION 02</span>
            <h3>MINI GAME - NEURO RUNNER</h3>
            <p>두 방향 운동 상상으로 장애물을 피하고 목적지에 도달합니다.</p>
            <ArrowUpRight />
          </Link>
          <Link to="/simulation?tab=applications&app=communication">
            <MessageSquareText size={40} />
            <span>APPLICATION 03</span>
            <h3>BCI Communication</h3>
            <p>두 방향 명령을 단계별 선택으로 확장해 의사를 표현합니다.</p>
            <ArrowUpRight />
          </Link>
        </div>
      </section>
    </main>
  );
}
