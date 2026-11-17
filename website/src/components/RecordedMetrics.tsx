import { useBCI } from "../store";

// Labels are used only to score predictions already received, never to choose a command.
export function RecordedMetrics() {
  const s = useBCI();
  const p = s.recordedPrediction;
  const observed = s.recordedTimeline.filter(
    (x) => x.trial_id <= s.recordedCursor && x.true_direction !== null,
  );
  const correct = observed.filter(
    (x) => x.predicted_direction === x.true_direction,
  ).length;
  const recalls = (["LEFT", "RIGHT"] as const).map((label) => {
    const trials = observed.filter((x) => x.true_direction === label);
    return trials.length
      ? trials.filter((x) => x.predicted_direction === label).length /
          trials.length
      : null;
  });
  const percent = (n: number | null) =>
    n === null ? "—" : `${(100 * n).toFixed(1)}%`;
  return (
    <section className="recorded-metrics" aria-label="실제 EEG 추론 지표">
      <dl className="monitor-stats">
        <div>
          <dt>Prediction</dt>
          <dd>{p?.predicted_direction ?? "—"}</dd>
        </div>
        <div>
          <dt>Decision score · P(RIGHT)</dt>
          <dd data-testid="decision-score">
            {p ? p.decision_score.toFixed(4) : "—"}
          </dd>
        </div>
        <div>
          <dt>Raw / centered logit</dt>
          <dd>
            {p
              ? `${p.raw_logit.toFixed(3)} / ${p.calibrated_logit.toFixed(3)}`
              : "—"}
          </dd>
        </div>
        <div>
          <dt>Inference latency</dt>
          <dd data-testid="inference-latency">
            {p ? `${p.latency_ms.toFixed(2)} ms` : "—"}
          </dd>
        </div>
        <div>
          <dt>Quality Gate</dt>
          <dd data-testid="quality-gate">{p?.quality.status ?? "—"}</dd>
        </div>
        <div>
          <dt>EOG / Gate threshold</dt>
          <dd>
            {p
              ? `${p.quality.eog_ptp_uv.toFixed(1)} / ${p.quality.threshold_uv.toFixed(1)} µV`
              : "—"}
          </dd>
        </div>
        <div>
          <dt>Accuracy · 관측 trial</dt>
          <dd data-testid="observed-accuracy">
            {percent(observed.length ? correct / observed.length : null)} · n=
            {observed.length}
          </dd>
        </div>
        <div>
          <dt>Balanced Accuracy</dt>
          <dd data-testid="observed-ba">
            {percent(
              recalls[0] === null || recalls[1] === null
                ? null
                : (recalls[0] + recalls[1]) / 2,
            )}
          </dd>
        </div>
      </dl>
    </section>
  );
}
