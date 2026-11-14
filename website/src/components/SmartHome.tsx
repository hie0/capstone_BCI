import { useEffect } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Lightbulb,
  PanelsTopLeft,
  Thermometer,
  Tv,
  RotateCcw,
  Radio,
  ArrowUpLeft,
} from "lucide-react";
import { useBCI, menus } from "../store";
import { Settings, Waveform, PlayButton } from "./Controls";
import { Room, RoomFallback, Scene } from "./Scenes";
import "./SmartHome.css";
import { configuredChannels } from "../data/channels";
import { selectedBackendModel } from "../data/backend";
const icons = [Lightbulb, PanelsTopLeft, Thermometer, Tv];
const actions = [
  ["조명 끄기", "조명 켜기"],
  ["커튼 닫기", "커튼 열기"],
  ["온도 −1°C", "온도 +1°C"],
  ["TV 끄기", "TV 켜기"],
];
export default function SmartHome() {
  const s = useBCI();
  const recorded = s.inputMode === "recorded";
  const channels = recorded
    ? (selectedBackendModel(s)?.active_channels ??
      configuredChannels(s.channelMode))
    : configuredChannels(s.channelMode);
  useEffect(() => {
    if (!s.isPlaying || s.inputMode !== "synthetic") return;
    const id = setInterval(() => {
      const state = useBCI.getState();
      if (!state.pending) state.command(Math.random() > 0.5 ? "LEFT" : "RIGHT");
    }, 2800 / s.speed);
    return () => clearInterval(id);
  }, [s.isPlaying, s.inputMode, s.speed]);
  useEffect(() => () => useBCI.getState().stop(), []);
  const statuses = [
    s.light ? "ON" : "OFF",
    s.curtains ? "OPEN" : "CLOSED",
    `${s.temperature}°C`,
    s.tv ? "ON" : "OFF",
  ];
  return (
    <>
      <div className="workspace-heading">
        <div>
          <span className="eyebrow">APPLICATION 01</span>
          <h2>Smart Home Control</h2>
        </div>
        <button className="button subtle" onClick={s.reset}>
          <RotateCcw size={14} /> Reset
        </button>
      </div>
      <div className="smart-layout">
        <Settings />
        <div className="room-panel panel">
          <div className="room-top">
            <span>
              <i className="status-dot" /> INTERACTIVE LIVING ROOM
            </span>
            <span className="badge">Application Simulation</span>
          </div>
          <div className="room-scene">
            <Scene room fallback={<RoomFallback />}>
              <Room />
            </Scene>
            <div
              className="scene-wall-temperature"
              aria-live="polite"
              aria-label={`현재 온도 ${s.temperature}도`}
            >
              <span className="wall-temperature-readout">
                <i className="classic-thermometer" aria-hidden="true" />
                <strong>{s.temperature}°C</strong>
              </span>
            </div>
            <div className="scene-caption">
              드래그하여 공간 둘러보기 <span>01 / LIVING ROOM</span>
            </div>
          </div>
          <div className="device-menu">
            {menus.map((name, i) => {
              const Icon = icons[i];
              return (
                <button
                  aria-label={`${name} 메뉴`}
                  aria-pressed={s.menu === i}
                  className={s.menu === i ? "active" : ""}
                  key={name}
                  onClick={() => s.choose(i)}
                >
                  <Icon size={19} />
                  <span>{name}</span>
                  <small>{statuses[i]}</small>
                </button>
              );
            })}
          </div>
          <div className="command-zone">
            <div className="mode-line">
              <span className="badge">
                {s.control ? "DEVICE CONTROL" : "MENU NAVIGATION"}
              </span>
              {s.control ? (
                <button className="text-button" onClick={s.back}>
                  <ArrowUpLeft size={14} /> 메뉴로 돌아가기
                </button>
              ) : (
                <span>좌우로 이동하거나 메뉴를 클릭하세요</span>
              )}
            </div>
            <div className="command-buttons">
              <button
                disabled={s.inputMode !== "manual"}
                className="left-command"
                aria-label={`LEFT ${s.control ? actions[s.menu][0] : "이전 메뉴"}`}
                title={s.control ? actions[s.menu][0] : "이전 메뉴"}
                onClick={() => s.command("LEFT")}
              >
                <ArrowLeft />
                <span>LEFT</span>
              </button>
              <button
                disabled={s.inputMode !== "manual"}
                className="right-command"
                aria-label={`RIGHT ${s.control ? actions[s.menu][1] : "다음 메뉴"}`}
                title={s.control ? actions[s.menu][1] : "다음 메뉴"}
                onClick={() => s.command("RIGHT")}
              >
                <span>RIGHT</span>
                <ArrowRight />
              </button>
            </div>
            {s.inputMode !== "manual" ? (
              <PlayButton
                playing={s.isPlaying}
                onClick={s.isPlaying ? s.stop : s.play}
                recorded={recorded}
              />
            ) : null}
          </div>
        </div>
        <aside className="monitor panel">
          <div className="panel-title">
            <Radio size={16} /> EEG control monitor <i className="status-dot" />
          </div>
          <span className="eyebrow">CURRENT MOTOR IMAGERY</span>
          <div
            className={`prediction ${s.currentCommand === "RIGHT" ? "purple" : ""}`}
            aria-live="polite"
          >
            {s.currentCommand === "LEFT" ? (
              <ArrowLeft size={30} />
            ) : s.currentCommand === "RIGHT" ? (
              <ArrowRight size={30} />
            ) : (
              <Radio size={28} />
            )}
            <strong>{s.currentCommand ?? "READY"}</strong>
            <span>
              {s.currentCommand
                ? recorded
                  ? `Recorded EEG · ${s.recordedPrediction?.quality.status ?? s.backendStatus}`
                  : "Predicted direction · 데모 입력"
                : "명령 입력을 기다리는 중"}
            </span>
          </div>
          <div className="confidence">
            <span>
              Confidence <small>확신도</small>
            </span>
            <b>{s.confidence === null ? "—" : `${s.confidence}%`}</b>
          </div>
          <div className="progress">
            <i style={{ width: `${s.confidence ?? 0}%` }} />
          </div>
          <Waveform
            channels={channels}
            playing={s.isPlaying || s.inputMode === "manual"}
            recorded={recorded}
            samples={s.recordedPrediction?.waveform}
          />
          <p className="small muted">
            {s.participantId} · {s.channelMode} · {channels.join(" · ")}
            {recorded && (
              <>
                <br />
                Calib20 · Reg-CSP + sLDA · {s.backendStatus}
              </>
            )}
          </p>
          <dl className="monitor-stats">
            <div>
              <dt>Active menu</dt>
              <dd>{menus[s.menu]}</dd>
            </div>
            <div>
              <dt>Device status</dt>
              <dd>{statuses[s.menu]}</dd>
            </div>
            <div>
              <dt>Command count</dt>
              <dd data-testid="command-count">
                {String(s.count).padStart(3, "0")}
              </dd>
            </div>
          </dl>
          <div className="log-heading">
            COMMAND HISTORY <span>최근 50개</span>
          </div>
          <div className="command-history" aria-live="polite">
            {s.history.length ? (
              s.history.map((h) => (
                <div key={h.id}>
                  <span className={h.direction === "LEFT" ? "cyan" : "purple"}>
                    {h.direction === "LEFT" ? "←" : "→"}
                  </span>
                  <p>
                    {h.message}
                    <small>{h.time}</small>
                  </p>
                  <span className="mono">{String(h.id).padStart(2, "0")}</span>
                </div>
              ))
            ) : (
              <p className="empty">
                첫 번째 명령을 보내보세요.
                <br />
                장치의 변화가 이곳에 기록됩니다.
              </p>
            )}
          </div>
        </aside>
      </div>
      <Keyboard />
    </>
  );
}
function Keyboard() {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        e.repeat ||
        e.ctrlKey ||
        e.metaKey ||
        e.altKey ||
        (e.target instanceof HTMLElement &&
          ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(e.target.tagName))
      )
        return;
      const s = useBCI.getState();
      if (s.inputMode === "manual" && ["l", "r"].includes(e.key.toLowerCase()))
        s.command(e.key.toLowerCase() === "l" ? "LEFT" : "RIGHT");
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  return null;
}
