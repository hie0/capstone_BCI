import { useSearchParams } from "react-router-dom";
import { useState } from "react";
import {
  House,
  Scan,
  ChartNoAxesCombined,
  Activity,
  ArrowUpRight,
  FlaskConical,
} from "lucide-react";
import SmartHome from "../components/SmartHome";
import Wearable from "../components/Wearable";
import Comparison from "../components/Comparison";
import Replay from "../components/Replay";
import { useBCI } from "../store";
export default function Simulation() {
  const [params] = useSearchParams();
  const [tab, setTab] = useState("applications");
  const [app, setApp] = useState(
    params.get("app") === "wearable" ? "wearable" : "home",
  );
  const s = useBCI();
  return (
    <main className="container simulation">
      <div className="breadcrumb">
        RESEARCH LAB <span>/</span> INTERACTIVE SIMULATION
      </div>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <i className="status-dot" /> EXPLORE THE POSSIBILITIES
          </div>
          <h1>
            뇌의 신호, 일상의 제어<span className="cyan">.</span>
          </h1>
          <p>운동 상상에서 시작되는 새로운 인터페이스를 직접 경험해보세요.</p>
        </div>
        <div className="lab-status">
          <FlaskConical size={17} />
          <span>
            INTERACTIVE LAB<small>장비 없이 체험하는 BCI 프로토타입</small>
          </span>
        </div>
      </div>
      <div
        className="main-tabs"
        role="tablist"
        aria-label="Simulation sections"
      >
        {[
          {
            id: "comparison",
            title: "Model Comparison",
            icon: ChartNoAxesCombined,
          },
          { id: "replay", title: "EEG Replay", icon: Activity },
          { id: "applications", title: "BCI Applications", icon: Scan },
        ].map((t) => (
          <button
            role="tab"
            aria-selected={tab === t.id}
            key={t.id}
            className={tab === t.id ? "active" : ""}
            onClick={() => {
              s.stop();
              setTab(t.id);
            }}
          >
            <t.icon size={17} />
            {t.title}
            {t.id === "applications" && (
              <span className="tab-tag">EXPLORE</span>
            )}
          </button>
        ))}
        <span className="shared-config">
          {s.channelMode.toUpperCase()} <i /> TTA {s.ttaEnabled ? "ON" : "OFF"}
        </span>
      </div>
      {tab === "applications" ? (
        <>
          <div className="app-picker">
            <button
              className={app === "home" ? "active" : ""}
              onClick={() => {
                s.stop();
                setApp("home");
              }}
            >
              <div className="app-icon">
                <House size={21} />
              </div>
              <div>
                <strong>Smart Home Control</strong>
                <span>두 가지 명령으로 연결하는 일상</span>
              </div>
              <ArrowUpRight size={18} />
            </button>
            <button
              className={app === "wearable" ? "active" : ""}
              onClick={() => {
                s.stop();
                setApp("wearable");
              }}
            >
              <div className="app-icon">
                <Scan size={21} />
              </div>
              <div>
                <strong>Wearable BCI Experience</strong>
                <span>더 적은 전극, 더 가벼운 가능성</span>
              </div>
              <ArrowUpRight size={18} />
            </button>
          </div>
          {app === "home" ? (
            <SmartHome />
          ) : (
            <Wearable onHome={() => setApp("home")} />
          )}
          <div className="how-it-works">
            <span>HOW IT WORKS</span>
            <div>
              <b>01</b> 운동 상상 입력
            </div>
            <i>→</i>
            <div>
              <b>02</b> LEFT / RIGHT 명령
            </div>
            <i>→</i>
            <div>
              <b>03</b> 가상 장치 제어
            </div>
            <small>실제 EEG 추론을 수행하지 않는 인터랙티브 데모입니다.</small>
          </div>
        </>
      ) : tab === "comparison" ? (
        <Comparison />
      ) : (
        <Replay />
      )}
      <div className="data-legend">
        <span>
          <i className="legend-dot research" /> Research Data{" "}
          <small>보고서의 연구 결과</small>
        </span>
        <span>
          <i className="legend-dot synthetic" /> Synthetic Demo{" "}
          <small>합성 파형과 명령</small>
        </span>
        <span>
          <i className="legend-dot application" /> Application Simulation{" "}
          <small>가상 장치 반응</small>
        </span>
      </div>
    </main>
  );
}
