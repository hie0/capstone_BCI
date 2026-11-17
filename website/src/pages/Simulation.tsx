import { useSearchParams } from "react-router-dom";
import {
  House,
  Gamepad2,
  MessageSquareText,
  Scan,
  Headphones,
  ArrowUpRight,
  FlaskConical,
} from "lucide-react";
import SmartHome from "../components/SmartHome";
import WearableLanding, { WearableHero } from "../components/WearableLanding";
import { useBCI } from "../store";
import { useRecordedEEG } from "../useRecordedEEG";
import CommunicationBoard from "../components/CommunicationBoard";
import NeuroRunner from "../components/NeuroRunner";
export default function Simulation() {
  const [params, setParams] = useSearchParams();
  const requestedApp = params.get("app");
  const app = requestedApp === "game" || requestedApp === "communication" ? requestedApp : "home";
  const tab =
    params.get("tab") === "applications" ||
    ["home", "game", "communication"].includes(params.get("app") ?? "")
      ? "applications"
      : "wearable";
  const s = useBCI();
  const navigate = (nextTab: "wearable" | "applications", nextApp = app) => {
    s.stop();
    setParams(
      nextTab === "wearable"
        ? { tab: "wearable" }
        : { tab: "applications", app: nextApp },
    );
  };
  useRecordedEEG(tab === "applications" && app === "home");
  return (
    <main
      className={`container simulation ${tab === "applications" ? "applications-active" : ""} ${tab === "applications" && app === "home" ? "smart-home-active" : ""}`}
    >
      <div className="breadcrumb">
        RESEARCH LAB <span>/</span> INTERACTIVE SIMULATION
      </div>
      {tab === "applications" ? (
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
      ) : (
        <WearableHero />
      )}
      <div
        className="main-tabs"
        role="tablist"
        aria-label="Simulation sections"
      >
        {[
          { id: "wearable", title: "Wearable BCI", icon: Headphones },
          { id: "applications", title: "BCI Applications", icon: Scan },
        ].map((t) => (
          <button
            role="tab"
            aria-selected={tab === t.id}
            key={t.id}
            className={tab === t.id ? "active" : ""}
            onClick={() => {
              navigate(t.id as "wearable" | "applications");
            }}
          >
            <t.icon size={17} />
            {t.title}
          </button>
        ))}
        {tab === "applications" && (
          <span className="shared-config">
            {s.inputMode === "recorded" && s.recordedLowChannel
              ? "LOW CHANNEL"
              : s.channelMode.toUpperCase()}{" "}
            <i /> TTA {s.ttaEnabled ? "ON" : "OFF"}
          </span>
        )}
      </div>
      {tab === "applications" ? (
        <>
          <div className="app-picker">
            <button
              className={app === "home" ? "active" : ""}
              onClick={() => {
                navigate("applications", "home");
              }}
            >
              <div className="app-icon">
                <House size={21} />
              </div>
              <div>
                <strong>SMART HOME 제어</strong>
                <span>자극 부위·신호·장치 반응을 한 화면에서</span>
              </div>
              <ArrowUpRight size={18} />
            </button>
            <button
              className={app === "game" ? "active" : ""}
              onClick={() => {
                navigate("applications", "game");
              }}
            >
              <div className="app-icon">
                <Gamepad2 size={21} />
              </div>
              <div>
                <strong>MINI GAME - NEURO RUNNER</strong>
                <span>운동 상상으로 장애물을 피하는 3D 게임</span>
              </div>
              <ArrowUpRight size={18} />
            </button>
            <button
              className={app === "communication" ? "active" : ""}
              onClick={() => navigate("applications", "communication")}
            >
              <div className="app-icon">
                <MessageSquareText size={21} />
              </div>
              <div>
                <strong>BCI Communication</strong>
                <span>두 방향 명령을 여러 의사표현으로 확장</span>
              </div>
              <ArrowUpRight size={18} />
            </button>
          </div>
          {app === "home" ? (
            <SmartHome />
          ) : app === "game" ? (
            <NeuroRunner />
          ) : (
            <CommunicationBoard />
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
              <b>03</b> {app === "communication" ? "의사표현 선택" : "가상 장치 제어"}
            </div>
            <small>
              {s.inputMode === "recorded"
                ? "실제 기록 EEG와 세션별 보정 모델을 이용한 가상 장치 제어입니다."
                : "실제 EEG 추론을 수행하지 않는 인터랙티브 데모입니다."}
            </small>
          </div>
        </>
      ) : (
        <WearableLanding onHome={() => navigate("applications", "home")} />
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
