import { useEffect, useMemo, useState } from "react";
import { Play, Pause, RotateCcw } from "lucide-react";
import { Settings, Waveform } from "./Controls";
import { useBCI } from "../store";
import { createDemoReplay } from "../data/replay";
import { configuredChannels } from "../data/channels";
import { selectedBackendModel } from "../data/backend";
export default function Replay() {
  const s = useBCI();
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [channel, setChannel] = useState("C3");
  const recorded = s.inputMode === "recorded";
  const channels = recorded
    ? (selectedBackendModel(s)?.active_channels ??
      configuredChannels(s.channelMode))
    : configuredChannels(s.channelMode);
  const total = recorded
    ? (s.backendSessions.find((x) => x.session_id === s.sessionId)
        ?.n_online_trials ?? 0)
    : 30;
  const playingNow = recorded ? s.isPlaying : playing;
  useEffect(() => {
    if (recorded && s.recordedPrediction)
      setIndex(s.recordedPrediction.trial_id - 1);
  }, [recorded, s.recordedPrediction]);
  useEffect(() => {
    if (!channels.includes(channel)) setChannel("C3");
  }, [s.channelMode, channel]);
  const source = useMemo(
    () => createDemoReplay(s.modelId, s.channelMode),
    [s.modelId, s.channelMode],
  );
  useEffect(() => {
    setPlaying(false);
    setIndex(0);
  }, [s.participantId, s.sessionId]);
  useEffect(() => {
    if (!playing || recorded) return;
    const id = setInterval(
      () =>
        setIndex((i) => {
          if (i >= source.predictions.length - 1) {
            setPlaying(false);
            return i;
          }
          return i + 1;
        }),
      2000 / s.speed,
    );
    return () => clearInterval(id);
  }, [playing, recorded, s.speed, source.predictions.length]);
  const current = s.recordedPrediction;
  const record = recorded
    ? current
      ? {
          trialId: current.trial_id,
          timestamp: current.timestamp,
          predictedLabel: current.predicted_direction,
          score: Math.max(current.probability_right, current.probability_left),
        }
      : null
    : source.predictions[index];
  return (
    <>
      <div className="workspace-heading">
        <div>
          <span className="eyebrow">
            {recorded ? "RECORDED EEG" : "SYNTHETIC DEMO"}
          </span>
          <h2>
            EEG Replay <span>신호에서 명령까지</span>
          </h2>
        </div>
        <span className="badge">
          {recorded ? s.backendStatus : "실제 기록 데이터 미연결"}
        </span>
      </div>
      <div className="replay-layout">
        <Settings compact />
        <div className="panel replay-main">
          <div className="row">
            <h3>EEG waveform</h3>
            <label>
              Channel
              <select
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
              >
                {channels.map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
          </div>
          <Waveform
            playing={playingNow}
            phase={index}
            channels={[channel]}
            large
            recorded={recorded}
            samples={current?.waveform}
          />
          <div className="row">
            <span className="cyan">← LEFT</span>
            <span className="purple">RIGHT →</span>
            <span>
              {recorded ? "Recorded" : "합성"} trial{" "}
              {recorded ? (record?.trialId ?? "—") : index + 1} / {total} ·{" "}
              {record?.timestamp ?? "—"}s
            </span>
          </div>
          <h3>Prediction timeline</h3>
          <div className="timeline">
            {(recorded
              ? Array.from({ length: total }, (_, i) => {
                  const p = s.recordedTimeline.find(
                    (x) => x.trial_id === i + 1,
                  );
                  return {
                    trialId: i + 1,
                    predictedLabel: p?.predicted_direction ?? null,
                  };
                })
              : source.predictions
            ).map((p, i) => (
              <button
                key={p.trialId}
                aria-label={`Trial ${p.trialId}: ${p.predictedLabel}`}
                aria-current={index === i}
                className={`${p.predictedLabel?.toLowerCase() ?? ""} ${index === i ? "selected" : ""}`}
                onClick={() => {
                  setIndex(i);
                  if (recorded) s.seekRecorded(i);
                }}
              >
                {p.predictedLabel === "LEFT"
                  ? "←"
                  : p.predictedLabel === "RIGHT"
                    ? "→"
                    : "·"}
              </button>
            ))}
          </div>
          <div className="replay-prediction">
            <strong
              className={record?.predictedLabel === "LEFT" ? "cyan" : "purple"}
            >
              {record?.predictedLabel ?? "READY"}
            </strong>
            <span>
              {recorded ? "모델 출력" : "합성 confidence"}{" "}
              {record ? `${Math.round((record.score ?? 0) * 100)}%` : "—"} ·{" "}
              {recorded
                ? `정답 ${current?.true_direction ?? "—"} · ${current?.quality.status ?? "대기"}`
                : "정답 라벨 없음"}
            </span>
          </div>
          <input
            aria-label="Replay position"
            type="range"
            min="0"
            max={Math.max(0, total - 1)}
            value={index}
            onChange={(e) => {
              const i = Number(e.target.value);
              setIndex(i);
              if (recorded) s.seekRecorded(i);
            }}
          />
          <div className="row">
            <button
              className="button primary"
              onClick={() => {
                if (recorded) {
                  if (s.isPlaying) s.stop();
                  else {
                    if (s.recordedCursor >= total) s.seekRecorded(0);
                    s.play();
                  }
                  return;
                }
                if (index === 29) setIndex(0);
                setPlaying(!playing);
              }}
            >
              {playingNow ? <Pause size={16} /> : <Play size={16} />}{" "}
              {playingNow ? "Pause" : "Play"}
            </button>
            <button
              className="button"
              onClick={() => {
                setPlaying(false);
                setIndex(0);
                if (recorded) s.seekRecorded(0);
              }}
            >
              <RotateCcw size={16} /> Reset replay
            </button>
          </div>
          <p className="source-note">
            {recorded ? (
              "실제 기록 EEG를 세션별 Calib20 모델과 WebSocket으로 추론합니다. 파형과 라벨은 선택한 원본 세션에서 가져옵니다."
            ) : (
              <>
                파형·예측 모두 UI 설명용 합성 데이터입니다. Participant와
                Session은 데모 식별자이며 연구 참여자의 기록을 재생하지
                않습니다. 실제 CSV/예측 JSON 어댑터는 미연결 상태입니다.
              </>
            )}
          </p>
        </div>
      </div>
    </>
  );
}
