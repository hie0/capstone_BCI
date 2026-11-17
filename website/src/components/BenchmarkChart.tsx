import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Rectangle,
} from "recharts";
import { Info } from "lucide-react";
import {
  comparisonConditions,
  percentagePointDelta,
  type ComparisonRow,
} from "../data/researchBenchmarks";
import "./BenchmarkChart.css";

type Metric = "Macro-F1" | "BA" | "AUC";
const formatValue = (value: number, metric: Metric) =>
  metric === "AUC" ? value.toFixed(4) : `${value.toFixed(2)}%`;
type ShapeProps = {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  fill?: string;
  payload?: ComparisonRow;
  condition: "baseline" | "lowTta";
  metric: Metric;
  showGain: boolean;
};
function ComparisonBar({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  fill,
  payload,
  condition,
  metric,
  showGain,
}: ShapeProps) {
  if (!payload) return null;
  const value = payload[condition];
  const label = `${payload.participant} · ${comparisonConditions.find((c) => c.key === condition)!.name} · ${metric} ${formatValue(value, metric)}`;
  const highest = Math.max(payload.baseline, payload.lowTta);
  const gainY = y - ((highest - value) * height) / (value - 50) - 18;
  return (
    <g
      role="img"
      aria-label={label}
      data-participant={payload.participant}
      data-condition={condition}
    >
      <title>{label}</title>
      <Rectangle
        x={x}
        y={y}
        width={width}
        height={height}
        fill={fill}
        radius={[7, 7, 0, 0]}
      />
      {showGain && condition === "lowTta" && (
        <text
          className="benchmark-gain-label"
          x={x - 2}
          y={gainY}
          textAnchor="middle"
        >
          {percentagePointDelta(value - payload.baseline)}
        </text>
      )}
    </g>
  );
}
function BenchmarkTooltip({
  active,
  label,
  rows,
  metric,
}: {
  active?: boolean;
  label?: string | number;
  rows: ComparisonRow[];
  metric: Metric;
}) {
  const row = rows.find((item) => item.participant === label);
  if (!active || !row) return null;
  return (
    <div className="benchmark-tooltip">
      <strong>
        {row.participant === "ALL" ? "ALL · 4인 평균" : row.participant}
      </strong>
      <span>{metric} · 16ch Baseline 대비 차이</span>
      {comparisonConditions.map((c) => (
        <div key={c.key}>
          <span>
            <i style={{ background: c.color }} />
            {c.name}
          </span>
          <b>{formatValue(row[c.key], metric)}</b>
          <small>
            {metric === "AUC"
              ? `+${(row[c.key] - row.baseline).toFixed(4)}`
              : percentagePointDelta(row[c.key] - row.baseline)}
          </small>
        </div>
      ))}
    </div>
  );
}

export function MetricInfo({ metric }: { metric: Metric }) {
  const content = {
    "Macro-F1": {
      title: "Macro-F1이란?",
      description:
        "좌·우 운동 상상 클래스의 정밀도와 재현율을 함께 고려하고, 두 클래스의 F1-score를 동일한 비중으로 평균한 지표입니다.",
      formulas: [
        "F1 = 2 × Precision × Recall / (Precision + Recall)",
        "Macro-F1 = (F1_LEFT + F1_RIGHT) / 2",
      ],
    },
    BA: {
      title: "BA란?",
      description:
        "Balanced Accuracy는 좌·우 클래스의 재현율을 동일한 비중으로 평균합니다. 클래스별 데이터 수가 다르더라도 한쪽 클래스의 성능에 치우치지 않게 평가합니다.",
      formulas: ["BA = (Recall_LEFT + Recall_RIGHT) / 2"],
    },
    AUC: {
      title: "AUC란?",
      description:
        "AUC는 분류 임계값을 바꾸었을 때의 민감도와 오탐률 관계를 종합한 지표입니다. 1에 가까울수록 좌·우 운동 상상을 안정적으로 구분합니다.",
      formulas: ["AUC = Area Under the ROC Curve", "0.5 = 무작위 수준 · 1.0 = 완전 분리"],
    },
  }[metric];
  return (
    <details className="macro-f1-info" key={metric}>
      <summary aria-label={`${metric} 지표 설명`}>
        <Info size={14} />
        <span>{metric}</span>
      </summary>
      <div>
        <strong>{content.title}</strong>
        <p>{content.description}</p>
        {content.formulas.map((formula) => <code key={formula}>{formula}</code>)}
      </div>
    </details>
  );
}

export function MacroF1Info() {
  return <MetricInfo metric="Macro-F1" />;
}

export function BenchmarkValueTable({
  rows,
  label = "Macro-F1",
  metric = "Macro-F1",
}: {
  rows: ComparisonRow[];
  label?: string;
  metric?: Metric;
}) {
  return (
    <details className="benchmark-values">
      <summary>{label} 수치 표 보기</summary>
      <div className="benchmark-table-scroll">
        <table>
          <caption>
            {label}
            {metric === "AUC" ? "" : " (%)"} · Historical research benchmark
          </caption>
          <thead>
            <tr>
              <th>Participant</th>
              {comparisonConditions.map((c) => (
                <th key={c.key}>{c.name}</th>
              ))}
              <th>Δ vs 16ch</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.participant}>
                <th>{row.participant}</th>
                {comparisonConditions.map((c) => (
                  <td key={c.key}>{formatValue(row[c.key], metric)}</td>
                ))}
                <td>
                  {metric === "AUC"
                    ? `+${(row.lowTta - row.baseline).toFixed(4)}`
                    : percentagePointDelta(row.lowTta - row.baseline)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
export default function BenchmarkChart({
  rows,
  label,
  metric = "Macro-F1",
  showGain = false,
}: {
  rows: ComparisonRow[];
  label: string;
  metric?: Metric;
  showGain?: boolean;
}) {
  const auc = metric === "AUC";
  return (
    <div className="benchmark-chart" aria-label={label}>
      <div className="chart-legend benchmark-legend">
        {comparisonConditions.map((c) => (
          <span key={c.key}>
            <i style={{ background: c.color }} />
            {c.name}
          </span>
        ))}
      </div>
      <div
        className="benchmark-chart-scroll"
        role="region"
        aria-label={`${label} 그래프`}
      >
        <div className="benchmark-chart-canvas">
          <ResponsiveContainer width="100%" height={330}>
            <BarChart
              data={rows}
              margin={{ top: 28, right: 14, left: 0, bottom: 8 }}
              barGap={4}
              accessibilityLayer
            >
              <CartesianGrid stroke="#DCE5EB" vertical={false} />
              <XAxis
                dataKey="participant"
                tick={{ fill: "#526574", fontWeight: 700, fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={auc ? [0.5, 1] : [50, 100]}
                ticks={
                  auc ? [0.5, 0.6, 0.7, 0.8, 0.9, 1] : [50, 60, 70, 80, 90, 100]
                }
                allowDataOverflow
                tickFormatter={(v) => (auc ? Number(v).toFixed(1) : `${v}%`)}
                tick={{ fill: "#526574", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                width={54}
                label={{
                  value: metric,
                  angle: -90,
                  position: "insideLeft",
                  fill: "#526574",
                  fontSize: 10,
                  offset: 12,
                }}
              />
              <Tooltip
                content={<BenchmarkTooltip rows={rows} metric={metric} />}
                cursor={{ fill: "#EAF0F5", opacity: 0.5 }}
                wrapperStyle={{ zIndex: 20 }}
              />
              {comparisonConditions.map((c) => (
                <Bar
                  key={c.key}
                  dataKey={c.key}
                  name={c.name}
                  fill={c.color}
                  isAnimationActive={false}
                  shape={
                    <ComparisonBar
                      condition={c.key}
                      metric={metric}
                      showGain={showGain && !auc}
                    />
                  }
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <BenchmarkValueTable rows={rows} label={metric} metric={metric} />
    </div>
  );
}
