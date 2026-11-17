import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useBCI } from "../store";
import BenchmarkChart, {
  BenchmarkValueTable,
  MacroF1Info,
} from "./BenchmarkChart";
import {
  losoMacroF1,
  onlineMacroF1,
  onlinePosterBA,
  comparisonConditions,
  externalMacroF1,
  benchmarkStatistics,
  percentagePointDelta,
  type BenchmarkParticipant,
} from "../data/researchBenchmarks";
import { comparison, subjectResults, type ChannelMode } from "../data/research";

export function SubjectResultChart() {
  const [subject, setSubject] = useState<BenchmarkParticipant>("ALL");
  const [metric, setMetric] = useState<"Macro-F1" | "BA" | "AUC">("Macro-F1");
  const selected = subjectResults.find((item) => item.id === subject);
  const f1 = losoMacroF1.find((item) => item.participant === subject)!;
  const macro = metric === "Macro-F1";
  const legacySubjects = selected ? [selected] : subjectResults;
  const rows = legacySubjects.map((item) => ({
    participant: item.id,
    baseline: metric === "BA" ? item.baselineBA : item.baselineAUC,
    lowTta: metric === "BA" ? item.proposedBA : item.proposedAUC,
  }));
  const average = (
    key: "baselineBA" | "proposedBA" | "baselineAUC" | "proposedAUC",
  ) =>
    subjectResults.reduce((sum, item) => sum + item[key], 0) /
    subjectResults.length;
  const baseline = macro
    ? f1.baseline
    : selected
      ? metric === "BA"
        ? selected.baselineBA
        : selected.baselineAUC
      : average(metric === "BA" ? "baselineBA" : "baselineAUC");
  const proposed = macro
    ? f1.lowTta
    : selected
      ? metric === "BA"
        ? selected.proposedBA
        : selected.proposedAUC
      : average(metric === "BA" ? "proposedBA" : "proposedAUC");
  const formatValue = (value: number) =>
    metric === "AUC" ? value.toFixed(4) : `${value.toFixed(2)}%`;
  const modelDescriptions: Record<string, string> = {
    KGE: "OAS로 공분산을 안정화하고 리만 접공간 특징을 SVC로 분류",
    KHY: "SPD 공분산을 보정한 접공간 특징을 sLDA로 분류",
    OYJ: "리만 접공간과 CSP 특징을 결합해 RBF-SVC로 분류",
    WMJ: "정규화 CSP로 좌·우 판별 특징을 추출해 LDA로 분류",
  };
  return (
    <div className="subject-results-dashboard">
      <div className="subject-toolbar">
        <div className="subject-tabs" aria-label="피험자 선택">
          {(["ALL", "KGE", "KHY", "OYJ", "WMJ"] as const).map((id) => (
            <button
              key={id}
              className={subject === id ? "active" : ""}
              aria-pressed={subject === id}
              aria-label={
                id === "ALL" ? "ALL 4인 비교" : `${id} Participant ${id}`
              }
              onClick={() => setSubject(id)}
            >
              <strong>{id}</strong>
              <span>{id === "ALL" ? "4인 비교" : "피험자"}</span>
            </button>
          ))}
        </div>
        <div className="metric-control">
          <span>평가 지표</span>
          <div className="metric-tabs" aria-label="평가 지표 선택">
            {(["Macro-F1", "BA", "AUC"] as const).map((item) => (
              <button
                key={item}
                className={metric === item ? "active" : ""}
                aria-pressed={metric === item}
                onClick={() => setMetric(item)}
              >
                {item}
              </button>
            ))}
          </div>
          <MacroF1Info />
        </div>
      </div>
      <div className="subject-dashboard-body">
        <div className="subject-chart-card">
          <h3 className="benchmark-chart-title">
            Cross-session Generalization — LOSO {metric}
          </h3>
          <BenchmarkChart
            rows={
              macro
                ? selected
                  ? [f1]
                  : losoMacroF1.filter((row) => row.participant !== "ALL")
                : rows
            }
            metric={metric}
            label={`Cross-session Generalization — LOSO ${metric}`}
          />
        </div>
        <aside className="subject-summary" aria-live="polite">
          <span className="eyebrow">선택 결과 · {metric}</span>
          <div className="subject-identity">
            <strong>{subject}</strong>
            <span>
              {subject === "ALL" ? "4인 평균" : `Participant ${subject}`}
            </span>
          </div>
          <dl>
            {(macro
              ? comparisonConditions.map((c) => ({
                  name: c.name,
                  value: f1[c.key],
                }))
              : [
                  { name: "16ch Baseline", value: baseline },
                  { name: "Low Channel + TTA", value: proposed },
                ]
            ).map((item) => (
              <div className="benchmark-selected-score" key={item.name}>
                <dt>{item.name}</dt>
                <dd>{formatValue(item.value)}</dd>
              </div>
            ))}
            <div>
              <dt>채널 수</dt>
              <dd>{selected?.channels ?? "5ch / 7ch"}</dd>
            </div>
            <div>
              <dt>개선 폭 · vs 16ch</dt>
              <dd data-testid="loso-improvement">
                {metric === "AUC"
                  ? `+${(proposed - baseline).toFixed(4)}`
                  : percentagePointDelta(proposed - baseline)}
              </dd>
            </div>
            <div>
              <dt>모델명</dt>
              <dd>{selected?.model ?? "개별 최적 모델"}</dd>
            </div>
            <div>
              <dt>평가 규모</dt>
              <dd>
                {macro
                  ? subject === "ALL"
                    ? "4인 · 타 날짜 LOSO"
                    : `Participant ${subject} · 타 날짜 LOSO`
                  : selected
                    ? `${selected.sessions} · ${selected.trials}회`
                    : "18개 런 · 1,440회"}
              </dd>
            </div>
          </dl>
        </aside>
      </div>
      <div className="model-roster">
        <div className="model-roster-heading">
          <span>개인별 최적 모델</span>
          <strong>
            각 피험자의 신호 특성에 맞는 최적 조합을 적용했습니다.
          </strong>
        </div>
        <div className="model-roster-grid">
          {subjectResults.map((item) => (
            <div key={item.id}>
              <span>
                {item.id} · {item.channels}
              </span>
              <strong>{item.model}</strong>
              <p>{modelDescriptions[item.id]}</p>
            </div>
          ))}
        </div>
        <div className="external-model">
          <div>
            <span>추가 외부 검증 · PhysioNet 100명</span>
            <strong>100명에게 동일한 공통 파이프라인을 적용했습니다.</strong>
            <p>
              핵심 5~7채널 선택 → OAS 공분산 안정화 → 리만 접공간 특징 →
              CausalEA 입력 정렬 → CausalLogitCenter 출력 영점 보정
            </p>
            <div className="external-f1-conditions">
              {externalMacroF1
                .filter((_, index) => index === 0 || index === 3)
                .map((item) => (
                  <span key={item.condition}>
                    {item.condition}
                    <b>
                      {item.mean.toFixed(2)} ± {item.sd.toFixed(2)}%
                    </b>
                  </span>
                ))}
            </div>
          </div>
          <div className="external-model-result">
            <span>평균 Macro-F1</span>
            <strong>59.33% → 65.77%</strong>
            <b>+6.44%p · 74/100명 성능 향상</b>
            <p className="benchmark-statistics">
              Paired t-test: p = {benchmarkStatistics.external.pairedT}
              <br />
              Wilcoxon: p = {benchmarkStatistics.external.wilcoxon}
              <br />N = 100 participants
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
export function ResultChart({
  metric = "Macro-F1",
}: {
  metric?: "Macro-F1" | "BA";
}) {
  const [showLegacyBA, setShowLegacyBA] = useState(false);
  if (metric === "BA") return <LegacyOnlineBAChart />;
  return (
    <div className="result-chart online-result-chart macro-f1-result-chart">
      <BenchmarkChart
        rows={onlineMacroF1}
        label="Online 50-session Performance — Macro-F1"
        showGain
      />
      <div className="online-chart-summary">
        <span>4인 평균 Macro-F1</span>
        <strong>67.46% → 74.23%</strong>
        <b>+6.77%p</b>
      </div>
      <p className="benchmark-context-note">
        4인 전원 16ch Baseline 대비 Macro-F1 향상 · Historical research
        benchmark · ArtGate90 적용
      </p>
      <p className="benchmark-statistics">
        <strong>50-session paired tests</strong>
        <br />
        Paired t-test: p = {benchmarkStatistics.online.pairedT}
        <br />
        Wilcoxon signed-rank test: p = {benchmarkStatistics.online.wilcoxon}
        <br />N = 50 sessions · 세션 단위 평균 차이 +6.79%p. 위의 +6.77%p는 4인
        균등 평균입니다.
      </p>
      <details
        className="legacy-ba-details"
        onToggle={(event) => setShowLegacyBA(event.currentTarget.open)}
      >
        <summary>기존 BA 보조 지표 보기</summary>
        {showLegacyBA && (
          <>
            <BenchmarkValueTable
              rows={onlinePosterBA}
              label="Online BA · poster"
            />
            <h4 className="benchmark-chart-title">
              기존 현장 라이브 대비 보정 결과 — BA
            </h4>
            <div className="benchmark-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>기존 BA 평가</th>
                    <th>현장 라이브</th>
                    <th>보정 결과</th>
                    <th>차이</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.map((item) => (
                    <tr key={item.name}>
                      <th>{item.name}</th>
                      <td>{item.baselineBA.toFixed(2)}%</td>
                      <td>{item.adjustedBA.toFixed(2)}%</td>
                      <td>{percentagePointDelta(item.improvement)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              위 BA 코호트 표는 현장 라이브와 보정 결과의 비교이며, 새로운
              Macro-F1의 16ch Baseline 비교와 다릅니다. 기존 BA 데이터와 유의성
              값은 보조 지표로 보존했습니다.
            </p>
          </>
        )}
      </details>
    </div>
  );
}
function LegacyOnlineBAChart() {
  return (
    <div className="result-chart online-result-chart">
      <div className="chart-legend online-legend">
        <span>
          <i className="baseline" />
          실전 온라인 정확도
        </span>
        <span>
          <i className="proposed" />
          영점조절 적용 후
        </span>
      </div>
      <ResponsiveContainer width="100%" height={310}>
        <BarChart
          data={comparison}
          margin={{ top: 25, right: 20, left: 0, bottom: 8 }}
        >
          <CartesianGrid stroke="#DCE5EB" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: "#526574", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            unit="%"
            tick={{ fill: "#526574", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "#FFFFFF",
              border: "1px solid #DCE5EB",
              borderRadius: 12,
              color: "#263746",
              boxShadow: "0 10px 28px rgba(37, 63, 85, 0.12)",
            }}
            formatter={(value, _name, item) => [
              `${Number(value).toFixed(2)}% BA`,
              item.dataKey === "baselineBA"
                ? "실전 온라인 정확도"
                : "영점조절 적용 후",
            ]}
            labelFormatter={(label) => {
              const row = comparison.find((item) => item.name === label);
              return row
                ? `${label} · ${row.trials.toLocaleString()}회 · ${row.significance}`
                : label;
            }}
          />
          <Bar
            isAnimationActive={false}
            dataKey="baselineBA"
            name="실전 온라인 정확도"
            fill="#A6B4C0"
            radius={[5, 5, 0, 0]}
            maxBarSize={64}
            label={{
              position: "top",
              fill: "#263746",
              formatter: (v: unknown) => `${Number(v).toFixed(2)}%`,
            }}
          />
          <Bar
            isAnimationActive={false}
            dataKey="adjustedBA"
            name="영점조절 적용 후"
            fill="#5F877F"
            radius={[5, 5, 0, 0]}
            maxBarSize={64}
            label={{
              position: "top",
              fill: "#263746",
              formatter: (v: unknown) => `${Number(v).toFixed(2)}%`,
            }}
          />
        </BarChart>
      </ResponsiveContainer>
      <div className="online-chart-summary">
        <span>50세션 통합</span>
        <strong>54.50% → 74.71%</strong>
        <b>+20.21%p</b>
      </div>
    </div>
  );
}
export default function Comparison() {
  const s = useBCI();
  const [dataset, setDataset] = useState("online");
  const [metric, setMetric] = useState("BA");
  return (
    <>
      <div className="workspace-heading">
        <div>
          <span className="eyebrow">RESEARCH DATA</span>
          <h2>
            Model Comparison <span>조건을 함께 읽는 연구 결과</span>
          </h2>
        </div>
        <span className="badge research">보고서 요약값</span>
      </div>
      <div className="panel">
        <div className="comparison-filters">
          <label>
            Participant
            <select>
              <option>4인 전체 · 상세 결과는 아래 차트</option>
            </select>
          </label>
          <label>
            Evaluation dataset
            <select
              value={dataset}
              onChange={(e) => setDataset(e.target.value)}
            >
              <option value="online">온라인 50세션 사후 재분석</option>
              <option value="loso">LOSO</option>
              <option value="live">실시간 라이브</option>
            </select>
          </label>
          <label>
            Channel configuration
            <select
              value={s.channelMode}
              onChange={(e) =>
                s.setSettings({ channelMode: e.target.value as ChannelMode })
              }
            >
              <option value="16ch">16ch</option>
              <option value="5ch">5ch · Low-channel 통합</option>
              <option value="7ch">7ch · Low-channel 통합</option>
            </select>
          </label>
          <label>
            Metric
            <select
              aria-label="Metric"
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
            >
              <option>BA</option>
              <option>AUC</option>
            </select>
          </label>
          <button
            className={`button ${s.ttaEnabled ? "active" : ""}`}
            aria-pressed={s.ttaEnabled}
            onClick={() => s.setSettings({ ttaEnabled: !s.ttaEnabled })}
          >
            TTA {s.ttaEnabled ? "ON" : "OFF"}
          </button>
        </div>
        {dataset === "online" && metric === "BA" ? (
          <ResultChart metric="BA" />
        ) : (
          <div className="metric-empty">
            <span>
              {dataset === "loso"
                ? "LOSO 평균"
                : dataset === "live"
                  ? "실시간 라이브 평균"
                  : "온라인 사후 재분석"}
            </span>
            <strong>
              {dataset === "loso"
                ? metric === "BA"
                  ? "76.06%"
                  : "0.8100"
                : dataset === "live" && metric === "BA"
                  ? "54.50%"
                  : "미제공"}
            </strong>
            <p>이 평가의 채널 구성·TTA별 상세 비교값은 제공되지 않았습니다.</p>
          </div>
        )}
        <p className="source-note">
          서로 다른 평가 조건을 직접 비교할 때는 세션 수와 트라이얼 수를 함께
          확인하세요.
        </p>
      </div>
      <div className="panel subject-comparison-panel">
        <div className="panel-title">
          피험자별 LOSO 결과{" "}
          <span className="badge research">4명 · 18개 런</span>
        </div>
        <SubjectResultChart />
      </div>
      <div className="insight-row">
        <div>
          <span>LOSO IMPROVEMENT</span>
          <strong>
            +7.78 <small>%p</small>
          </strong>
          <p>16ch 68.28% → 제안 모델 76.06%</p>
        </div>
        <div>
          <span>ONLINE 18 SESSIONS</span>
          <strong>
            +21.80 <small>%p</small>
          </strong>
          <p>53.90% → 75.70% · p = 0.020</p>
        </div>
        <div>
          <span>ONLINE 50 SESSIONS</span>
          <strong>
            74.71<small>%</small>
          </strong>
          <p>3,910회 · +20.21%p · p &lt; 10⁻¹⁷</p>
        </div>
      </div>
    </>
  );
}
