import { useEffect, useState } from "react";
import { Activity, Settings2, Play, Pause, Info } from "lucide-react";
import { useBCI } from "../store";
import type { ChannelMode } from "../data/research";
export function Settings({ compact = false }: { compact?: boolean }) {
  const s = useBCI();
  return (
    <div className="settings panel">
      <div className="panel-title">
        <Settings2 size={16} />{" "}
        {compact ? "공유 실험 설정" : "Control settings"}
      </div>
      <label>
        Input mode
        <select
          value={s.inputMode}
          onChange={(e) =>
            s.setSettings({
              inputMode: e.target.value as "manual" | "synthetic",
            })
          }
        >
          <option value="manual">Manual Demo</option>
          <option value="synthetic">Simulated EEG</option>
          <option value="recorded" disabled>
            Recorded EEG · 데이터 연결 필요
          </option>
        </select>
      </label>
      <div className="field-pair">
        <label>
          Participant
          <select
            value={s.participantId}
            onChange={(e) => s.setSettings({ participantId: e.target.value })}
          >
            <option value="demo-01">Demo P01</option>
            <option value="demo-02">Demo P02</option>
          </select>
        </label>
        <label>
          Session
          <select
            value={s.sessionId}
            onChange={(e) => s.setSettings({ sessionId: e.target.value })}
          >
            <option value="session-01">Session 01</option>
            <option value="session-02">Session 02</option>
          </select>
        </label>
      </div>
      <label>
        Model
        <select
          value={s.modelId}
          onChange={(e) => s.setSettings({ modelId: e.target.value })}
        >
          <option value="low-channel-tta">Low-channel pipeline</option>
          <option value="baseline">16ch baseline pipeline</option>
        </select>
      </label>
      <label>
        Channel configuration
        <select
          aria-label="Channel configuration"
          value={s.channelMode}
          onChange={(e) =>
            s.setSettings({ channelMode: e.target.value as ChannelMode })
          }
        >
          <option value="16ch">Full 16 Channels</option>
          <option value="5ch">Core 5 Channels</option>
          <option value="7ch">Extended 7 · 콘셉트</option>
        </select>
      </label>
      <div className="toggle-row">
        <span>
          TTA <small>Test-time adaptation</small>
        </span>
        <button
          role="switch"
          aria-checked={s.ttaEnabled}
          aria-label="TTA"
          className={`switch ${s.ttaEnabled ? "on" : ""}`}
          onClick={() => s.setSettings({ ttaEnabled: !s.ttaEnabled })}
        >
          <i />
        </button>
      </div>
      <label>
        Playback speed <b>{s.speed}×</b>
        <input
          aria-label="Playback speed"
          type="range"
          min="0.5"
          max="2"
          step="0.5"
          value={s.speed}
          onChange={(e) => s.setSettings({ speed: Number(e.target.value) })}
        />
      </label>
      <div className="note">
        <Info size={14} />
        <span>
          설정은 모든 체험에 공유됩니다. 모델·TTA는 구성만 표시하며 실제 추론은
          실행하지 않습니다.
        </span>
      </div>
    </div>
  );
}
export function Waveform({
  playing = true,
  phase = 0,
  channels = ["C3", "Cz", "C4"],
  large = false,
}: {
  playing?: boolean;
  phase?: number;
  channels?: string[];
  large?: boolean;
}) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setTick((t) => t + 0.17), 100);
    return () => clearInterval(id);
  }, [playing]);
  return (
    <div className={`waveform ${large ? "large" : ""}`}>
      <div className="wave-header">
        <Activity size={13} />
        <span>Synthetic EEG Demo</span>
        <span className="mono">µV · illustrative</span>
      </div>
      <svg
        viewBox={`0 0 500 ${channels.length * 48}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="합성 EEG 파형"
      >
        <defs>
          <pattern
            id="grid"
            width="25"
            height="24"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M25 0H0V24"
              fill="none"
              stroke="#214057"
              strokeWidth=".5"
            />
          </pattern>
        </defs>
        <rect width="500" height="100%" fill="url(#grid)" />
        {channels.map((c, j) => (
          <g key={c}>
            <text x="4" y={j * 48 + 25} fill="#8aa2b9" fontSize="11">
              {c}
            </text>
            <path
              d={Array.from(
                { length: 240 },
                (_, i) =>
                  `${i === 0 ? "M" : "L"}${35 + i * 1.95},${24 + j * 48 + Math.sin(i * 0.36 + tick + phase + j * 2) * 8 + Math.sin(i * 0.89 + tick * 2 + phase + j) * 4 + Math.cos(i * 0.13 + tick) * 3}`,
              ).join(" ")}
              fill="none"
              stroke={j % 2 ? "#b58cff" : "#38dbe6"}
              strokeWidth="1.2"
            />
          </g>
        ))}
      </svg>
    </div>
  );
}
export function PlayButton({
  playing,
  onClick,
}: {
  playing: boolean;
  onClick: () => void;
}) {
  return (
    <button className="button primary" onClick={onClick}>
      {playing ? <Pause size={16} /> : <Play size={16} />}{" "}
      {playing ? "일시정지" : "자동 데모 시작"}
    </button>
  );
}
