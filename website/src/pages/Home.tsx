import { useState } from "react";
import { channelInfo } from "../data/research";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  BrainCircuit,
  Layers,
  Waves,
  Scan,
  House,
} from "lucide-react";
import { Scene, Atlas2D } from "../components/Scenes";
import { HeroBust } from "../components/HeroBust";
import { ResultChart } from "../components/Comparison";
export function Pipeline() {
  return (
    <div className="pipeline">
      {[
        { icon: Waves, title: "EEG acquisition", desc: "운동 상상 뇌파 입력" },
        { icon: Scan, title: "Channel selection", desc: "감각운동 중심 5~7ch" },
        { icon: Layers, title: "Stabilization", desc: "공분산 · 영점 안정화" },
        {
          icon: BrainCircuit,
          title: "Classification",
          desc: "LEFT / RIGHT 분류",
        },
        { icon: House, title: "Application", desc: "일상 속 인터페이스" },
      ].map((p, i) => (
        <div key={p.title}>
          <span className="mono">0{i + 1}</span>
          <p.icon size={25} />
          <strong>{p.title}</strong>
          <small>{p.desc}</small>
        </div>
      ))}
    </div>
  );
}
export default function Home() {
  const [selected, setSelected] = useState("C4");
  return (
    <main>
      <section className="container hero">
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
            <Link className="button" to="/research">
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
          ["16 → 5–7", "CHANNEL OPTIMIZATION", "핵심 채널 중심 최적화"],
          ["0.8100", "LOSO · MEAN AUC", "4인 제안 모델 평균"],
          ["76.06%", "LOSO · MEAN BA", "18개 런 · 1,440회"],
          ["74.71%", "ONLINE · 50 SESSIONS", "3,910회 · 영점조절 적용"],
        ].map(([v, l, d]) => (
          <div
            key={l}
            tabIndex={0}
            title={`출처: 사용자 제공 보고서 요약 · ${d}. 평가 조건 간 직접 비교에 유의하세요.`}
          >
            <span>{l}</span>
            <strong>{v}</strong>
            <small>{d} ⓘ</small>
          </div>
        ))}
      </section>
      <section className="container section">
        <div className="section-title">
          <div>
            <span className="eyebrow">01 / THE RESEARCH QUESTION</span>
            <h2>
              일상 속 BCI를 위해,
              <br />
              무엇을 줄이고 무엇을 지킬까요?
            </h2>
          </div>
          <p>
            채널 수를 늘리는 것만으로 안정성이 보장되지는 않습니다.
            <br />
            복잡한 입력과 세션 변화라는 두 가지 문제에 집중했습니다.
          </p>
        </div>
        <div className="problem-grid">
          <article>
            <span className="outline-number">01</span>
            <h3>공간적 제약</h3>
            <p>
              16채널의 복잡한 배치와 잡음. 운동 상상에 필요한 감각운동 영역을
              중심으로 입력 차원을 줄입니다.
            </p>
            <Link to="/research">
              채널 최적화 살펴보기 <ArrowUpRight size={16} />
            </Link>
          </article>
          <article>
            <span className="outline-number">02</span>
            <h3>시간적 변동</h3>
            <p>
              같은 사람의 신호도 세션마다 달라집니다. 공분산과 영점 안정화를
              통해 세션 간 변동에 대응합니다.
            </p>
            <Link to="/research">
              세션 적응 살펴보기 <ArrowUpRight size={16} />
            </Link>
          </article>
        </div>
      </section>
      <section className="container section channel-preview">
        <div>
          <span className="eyebrow">02 / LESS, BUT FOCUSED</span>
          <h2>
            핵심은, 필요한 신호에
            <br />
            집중하는 것.
          </h2>
          <p>
            F3, F4, C3, Cz, C4.
            <br />
            감각운동 중심의 5개 전극으로 살펴보는
            <br />더 간결한 인터페이스의 가능성.
          </p>
          <Link to="/simulation?app=wearable" className="button">
            웨어러블 구성 체험 <ArrowRight size={16} />
          </Link>
        </div>
        <Atlas2D mode="5ch" selected={selected} onSelect={setSelected} />
        <div className="channel-stat">
          <strong>
            68.75<small>%</small>
          </strong>
          <span>16ch → 5ch 전극 감축률</span>
          <p className="small">
            {selected} · {channelInfo(selected)}
          </p>
          <hr />
          <strong>136 → 15</strong>
          <span>대칭 공분산의 독립 원소 수</span>
        </div>
      </section>
      <section className="container section">
        <div className="section-title">
          <div>
            <span className="eyebrow">03 / FROM SIGNAL TO ACTION</span>
            <h2>신호를 이해하고, 명령으로 연결합니다.</h2>
          </div>
        </div>
        <Pipeline />
      </section>
      <section className="container section findings">
        <div>
          <span className="eyebrow">04 / RESEARCH FINDINGS</span>
          <h2>
            가능성과 한계를
            <br />
            함께 읽는 결과.
          </h2>
          <p>
            실전 온라인 50세션 3,910회에서 적응형 영점조절 적용 후 평균 BA는
            74.71%입니다.
          </p>
          <div className="live-metric">
            영점조절 전 평균 BA <strong>54.50%</strong>
            <small>적용 후 +20.21%p · p &lt; 10⁻¹⁷</small>
          </div>
          <Link to="/research" className="text-button">
            실험 결과와 평가 조건 <ArrowRight size={16} />
          </Link>
        </div>
        <div className="panel">
          <div className="panel-title">
            온라인 사후 재분석{" "}
            <span className="badge research">Research Data</span>
          </div>
          <ResultChart />
        </div>
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
          <Link to="/simulation">
            <House size={40} />
            <span>APPLICATION 01</span>
            <h3>Smart Home Control</h3>
            <p>LEFT와 RIGHT, 두 가지 명령으로 바뀌는 거실.</p>
            <ArrowUpRight />
          </Link>
          <Link to="/simulation?app=wearable">
            <Scan size={40} />
            <span>APPLICATION 02</span>
            <h3>Wearable BCI Experience</h3>
            <p>전극을 선택하고, 가벼운 디바이스의 가능성을 탐색하세요.</p>
            <ArrowUpRight />
          </Link>
        </div>
      </section>
    </main>
  );
}
