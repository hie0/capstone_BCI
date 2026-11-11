import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";
import { useBCI } from "../store";
import { comparison, sourceNote, type ChannelMode } from "../data/research";
export function ResultChart() {
  const s = useBCI();
  return (
    <div className="result-chart">
      <ResponsiveContainer width="100%" height={310}>
        <BarChart
          data={comparison}
          margin={{ top: 25, right: 20, left: 0, bottom: 8 }}
        >
          <CartesianGrid stroke="#203448" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: "#9aafc3", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            unit="%"
            tick={{ fill: "#9aafc3", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "#10243a",
              border: "1px solid #35516a",
              borderRadius: 8,
              color: "#e6f6ff",
            }}
            formatter={(v) => [`${v}%`, "Balanced accuracy"]}
          />
          <ReferenceLine
            y={54.48}
            stroke="#d6ae77"
            strokeDasharray="5 5"
            label={{
              value: "현장 라이브 54.48% · 별도 조건",
              fill: "#d6ae77",
              fontSize: 11,
              position: "insideTopRight",
            }}
          />
          <Bar
            isAnimationActive={false}
            dataKey="ba"
            radius={[5, 5, 0, 0]}
            maxBarSize={86}
            label={{
              position: "top",
              fill: "#dfedf7",
              formatter: (v: unknown) => `${v}%`,
            }}
          >
            {comparison.map((d) => (
              <Cell
                key={d.name}
                fill={
                  d.channels === (s.channelMode === "16ch" ? "16ch" : "low") &&
                  d.tta === s.ttaEnabled
                    ? "#00dce9"
                    : "#31516f"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
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
            <select disabled>
              <option>전체 평균 · 개인별 값 미제공</option>
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
              <option value="live">현장 라이브</option>
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
          <ResultChart />
        ) : (
          <div className="metric-empty">
            <span>
              {dataset === "loso"
                ? "LOSO 평균"
                : dataset === "live"
                  ? "현장 라이브 평균"
                  : "온라인 사후 재분석"}
            </span>
            <strong>
              {dataset === "loso"
                ? metric === "BA"
                  ? "76.64%"
                  : "0.8191"
                : dataset === "live" && metric === "BA"
                  ? "54.48%"
                  : "미제공"}
            </strong>
            <p>이 평가의 채널 구성·TTA별 상세 비교값은 제공되지 않았습니다.</p>
          </div>
        )}
        <p className="source-note">
          {sourceNote} LOSO의 구체적인 분할 단위는 원문 보고서 확인이
          필요합니다. 서로 다른 평가 조건을 직접적인 개선율로 해석하지 마세요.
        </p>
      </div>
      <div className="insight-row">
        <div>
          <span>CHANNEL OPTIMIZATION</span>
          <strong>
            +2.81 <small>%p</small>
          </strong>
          <p>16ch only → Low-channel only</p>
        </div>
        <div>
          <span>TEST-TIME ADAPTATION</span>
          <strong>
            +2.57 <small>%p</small>
          </strong>
          <p>Low-channel → Low-channel + TTA</p>
        </div>
        <div>
          <span>REAL-WORLD GAP</span>
          <strong>
            54.48<small>%</small>
          </strong>
          <p>현장 라이브 BA · 별도 평가 조건</p>
        </div>
      </div>
    </>
  );
}
