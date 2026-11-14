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
    <section aria-label="실제 EEG 추론 지표">
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
      <p className="small muted">
        현재까지 재생한 trial 전체 기준(품질 미달 포함). BA는 양쪽 정답이 관측된
        후 표시합니다. 기록 정답은 평가에만 사용합니다.
      </p>
      <p className="small muted">
        세션별 Calib20 재생 결과이며, 50세션 연구의 사후 최적 조건 선택 성능 및
        사전 고정 모델의 독립 실시간 검증과 구분합니다. Quality Gate는 제공된
        모델의 사후 ArtGate90 임계값을 그대로 사용합니다. Low Channel은 TTA
        선택에 따라 채널·모델 구성이 달라질 수 있어 TTA 단독 효과 비교가
        아닙니다.
      </p>
    </section>
  );
}
