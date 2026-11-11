import { useEffect, useMemo, useState } from "react";
import { Play, Pause, RotateCcw } from "lucide-react";
import { Settings, Waveform } from "./Controls";
import { useBCI } from "../store";
import { createDemoReplay } from "../data/replay";
import { electrodeNames } from "../data/research";
export default function Replay() {
  const s = useBCI();
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [channel, setChannel] = useState("C3");
  const source = useMemo(
    () => createDemoReplay(s.modelId, s.channelMode),
    [s.modelId, s.channelMode],
  );
  useEffect(() => {
    setPlaying(false);
    setIndex(0);
  }, [s.participantId, s.sessionId]);
  useEffect(() => {
    if (!playing) return;
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
  }, [playing, s.speed, source.predictions.length]);
  const record = source.predictions[index];
  return (
    <>
      <div className="workspace-heading">
        <div>
          <span className="eyebrow">SYNTHETIC DEMO</span>
          <h2>
            EEG Replay <span>신호에서 명령까지</span>
          </h2>
        </div>
        <span className="badge">실제 기록 데이터 미연결</span>
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
                {electrodeNames.map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
          </div>
          <Waveform
            playing={playing}
            phase={index}
            channels={[channel]}
            large
          />
          <div className="row">
            <span className="cyan">← LEFT</span>
            <span className="purple">RIGHT →</span>
            <span>
              합성 trial {index + 1} / 30 · {record.timestamp}s
            </span>
          </div>
          <h3>Prediction timeline</h3>
          <div className="timeline">
            {source.predictions.map((p, i) => (
              <button
                key={p.trialId}
                aria-label={`Trial ${p.trialId}: ${p.predictedLabel}`}
                aria-current={index === i}
                className={`${p.predictedLabel.toLowerCase()} ${index === i ? "selected" : ""}`}
                onClick={() => setIndex(i)}
              >
                {p.predictedLabel === "LEFT" ? "←" : "→"}
              </button>
            ))}
          </div>
          <div className="replay-prediction">
            <strong
              className={record.predictedLabel === "LEFT" ? "cyan" : "purple"}
            >
              {record.predictedLabel}
            </strong>
            <span>
              합성 confidence {Math.round((record.score ?? 0) * 100)}% · 정답
              라벨 없음
            </span>
          </div>
          <input
            aria-label="Replay position"
            type="range"
            min="0"
            max="29"
            value={index}
            onChange={(e) => setIndex(Number(e.target.value))}
          />
          <div className="row">
            <button
              className="button primary"
              onClick={() => {
                if (index === 29) setIndex(0);
                setPlaying(!playing);
              }}
            >
              {playing ? <Pause size={16} /> : <Play size={16} />}{" "}
              {playing ? "Pause" : "Play"}
            </button>
            <button
              className="button"
              onClick={() => {
                setPlaying(false);
                setIndex(0);
              }}
            >
              <RotateCcw size={16} /> Reset replay
            </button>
          </div>
          <p className="source-note">
            파형·예측 모두 UI 설명용 합성 데이터입니다. Participant와 Session은
            데모 식별자이며 연구 참여자의 기록을 재생하지 않습니다. 실제
            CSV/예측 JSON 어댑터는 미연결 상태입니다.
          </p>
        </div>
      </div>
    </>
  );
}
