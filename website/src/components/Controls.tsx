import { useEffect, useState } from "react";
import { Activity, Settings2, Play, Pause, Info } from "lucide-react";
import { useBCI } from "../store";
import { participantModels, type ParticipantId } from "../data/channels";
import { selectedBackendModel } from "../data/backend";
export function Settings({
  compact = false,
  embedded = false,
}: {
  compact?: boolean;
  embedded?: boolean;
}) {
  const s = useBCI();
  const recorded = s.inputMode === "recorded";
  const selectedSession = s.backendSessions.find(
    (x) => x.session_id === s.sessionId,
  );
  const actualModel = selectedBackendModel(s);
  return (
    <div className={embedded ? "" : "settings panel"}>
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
              inputMode: e.target.value as "manual" | "synthetic" | "recorded",
            })
          }
        >
          <option value="manual">Manual Demo</option>
          <option value="synthetic">Simulated EEG</option>
          <option value="recorded">Recorded EEG · 실제 추론</option>
        </select>
      </label>
      <div className="field-pair">
        <label>
          Participant
          <select
            value={s.participantId}
            onChange={(e) => s.setSettings({ participantId: e.target.value })}
          >
            {Object.entries(participantModels).map(([id, p]) => (
              <option value={id} key={id}>
                {id} · {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Session
          <select
            value={s.sessionId}
            onChange={(e) => s.setSettings({ sessionId: e.target.value })}
          >
            {recorded ? (
              s.backendSessions
                .filter((x) => x.participant_id === s.participantId)
                .map((x) => (
                  <option key={x.session_id} value={x.session_id}>
                    {x.session_id} · {x.n_online_trials} trials
                  </option>
                ))
            ) : (
              <>
                <option value="session-01">Session 01</option>
                <option value="session-02">Session 02</option>
              </>
            )}
          </select>
        </label>
      </div>
      <label>
        Model
        <select
          value={s.modelId}
          onChange={(e) => s.setSettings({ modelId: e.target.value })}
        >
          {recorded ? (
            <option value="online-calib20">
              Calib20 · Reg-CSP + sLDA
              {actualModel ? ` · ${actualModel.montage}` : ""}
            </option>
          ) : (
            <>
              {s.modelId === "visualization-only" && (
                <option value="visualization-only">
                  배치 탐색 · 모델 미연결
                </option>
              )}
              <option
                value={
                  participantModels[s.participantId as ParticipantId].modelId
                }
              >
                {participantModels[s.participantId as ParticipantId].modelName}
              </option>
              <option value="baseline" disabled>
                16ch OAS + TS + LR · 파일 미연결
              </option>
            </>
          )}
        </select>
      </label>
      <label>
        Channel configuration
        <select
          aria-label="Channel configuration"
          value={
            s.channelMode === "16ch" && !s.recordedLowChannel ? "16ch" : "low"
          }
          onChange={(e) =>
            s.setSettings(
              e.target.value === "low"
                ? recorded
                  ? { recordedLowChannel: true }
                  : {
                      channelMode:
                        participantModels[s.participantId as ParticipantId]
                          .channelMode,
                    }
                : { channelMode: "16ch" },
            )
          }
        >
          <option
            value="16ch"
            disabled={
              recorded
                ? !selectedSession?.available_models[
                    `16ch__tta_${s.ttaEnabled ? "on" : "off"}`
                  ]
                : true
            }
          >
            16ch
            {recorded
              ? ` · ${selectedSession?.available_models[`16ch__tta_${s.ttaEnabled ? "on" : "off"}`]?.montage ?? "연결 대기"}`
              : " · 실제 추론 미연결"}
          </option>
          <option
            value="low"
            disabled={
              recorded &&
              !selectedSession?.available_models[
                `low__tta_${s.ttaEnabled ? "on" : "off"}`
              ]
            }
          >
            Low Channel
            {recorded
              ? ` · ${selectedSession?.available_models[`low__tta_${s.ttaEnabled ? "on" : "off"}`]?.montage ?? "연결 대기"}`
              : ""}
          </option>
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
          {recorded
            ? `${s.backendStatus} · 실제 기록 EEG, 세션별 Calib20 모델. 품질 기준 미달 시 장치 명령은 보류합니다.`
            : "설정은 모든 체험에 공유됩니다. 모델·TTA는 구성만 표시하며 실제 추론은 실행하지 않습니다."}
          {s.backendError && <span role="alert">{s.backendError}</span>}
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
  recorded = false,
  samples,
}: {
  playing?: boolean;
  phase?: number;
  channels?: string[];
  large?: boolean;
  recorded?: boolean;
  samples?: Record<string, number[]> | null;
}) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!playing || recorded) return;
    const id = setInterval(() => setTick((t) => t + 0.17), 100);
    return () => clearInterval(id);
  }, [playing, recorded]);
  return (
    <div className={`waveform ${large ? "large" : ""}`}>
      <div className="wave-header">
        <Activity size={13} />
        <span>{recorded ? "Recorded EEG" : "Synthetic EEG Demo"}</span>
        <span className="mono">
          µV · {recorded ? "recorded" : "illustrative"}
        </span>
      </div>
      <svg
        viewBox={`0 0 500 ${channels.length * 48}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={recorded ? "실제 EEG 파형" : "합성 EEG 파형"}
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
              stroke="#DCE5EB"
              strokeWidth=".5"
            />
          </pattern>
        </defs>
        <rect width="500" height="100%" fill="url(#grid)" />
        {channels.map((c, j) => (
          <g key={c}>
            <text x="4" y={j * 48 + 25} fill="#697B89" fontSize="11">
              {c}
            </text>
            <path
              d={
                recorded
                  ? (() => {
                      const values = samples?.[c];
                      if (!values?.length)
                        return `M35 ${24 + j * 48}L500 ${24 + j * 48}`;
                      const mean =
                        values.reduce((a, b) => a + b, 0) / values.length;
                      const scale =
                        18 /
                        Math.max(1, ...values.map((v) => Math.abs(v - mean)));
                      return values
                        .map(
                          (v, i) =>
                            `${i ? "L" : "M"}${35 + (i * 465) / Math.max(1, values.length - 1)},${24 + j * 48 - (v - mean) * scale}`,
                        )
                        .join(" ");
                    })()
                  : Array.from(
                      { length: 240 },
                      (_, i) =>
                        `${i === 0 ? "M" : "L"}${35 + i * 1.95},${24 + j * 48 + Math.sin(i * 0.36 + tick + phase + j * 2) * 8 + Math.sin(i * 0.89 + tick * 2 + phase + j) * 4 + Math.cos(i * 0.13 + tick) * 3}`,
                    ).join(" ")
              }
              fill="none"
              stroke={j % 2 ? "#8A79AF" : "#527C98"}
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
  recorded = false,
}: {
  playing: boolean;
  onClick: () => void;
  recorded?: boolean;
}) {
  return (
    <button className="button primary" onClick={onClick}>
      {playing ? <Pause size={16} /> : <Play size={16} />}{" "}
      {playing ? "일시정지" : recorded ? "실제 EEG 재생" : "자동 데모 시작"}
    </button>
  );
}
