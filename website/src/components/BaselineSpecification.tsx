import { baseline16 as b } from "../data/channels";

export function BaselineSpecification() {
  return (
    <details className="panel" style={{ marginTop: 24 }}>
      <summary
        style={{ cursor: "pointer", color: "var(--primary)", fontWeight: 600 }}
      >
        16ch Baseline · 연구 모델 명세
      </summary>
      <dl style={{ lineHeight: 1.8, overflowWrap: "anywhere" }}>
        <dt>입력 채널</dt>
        <dd>{b.channels.join(" · ")}</dd>
        <dt>전처리 · MI 구간</dt>
        <dd>
          {b.filter.bandHz.join("–")} Hz {b.filter.order}차 {b.filter.type}{" "}
          대역통과 · {b.miWindowSeconds.join("–")}초 · {b.sampleRateHz} Hz
        </dd>
        <dt>공분산 추정</dt>
        <dd>{b.covariance} + SPD 정칙화 (λ ≥ 10⁻¹⁰)</dd>
        <dt>특징 추출</dt>
        <dd>
          TangentSpace(metric="{b.tangentMetric}") · {b.featureDimensions}차원
        </dd>
        <dt>분류기</dt>
        <dd>{b.classifier}</dd>
        <dt>TTA</dt>
        <dd>OFF · 공분산 중심화 EA 및 로짓 영점 보정 없음</dd>
        <dt>검증</dt>
        <dd>
          {b.validation} · 연구팀 제공 누수율 {b.reportedLeakagePercent}%
        </dd>
      </dl>
      <p className="source-note">
        연구팀 제공 baseline 명세입니다. 기존 LOSO·온라인 결과와 평가 조건이
        다르며 이 LORO baseline의 성능 수치는 아직 제공되지 않았습니다. 실제
        모델 파일은 연결되지 않았습니다.
      </p>
    </details>
  );
}
