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
import {
  comparison,
  sourceNote,
  subjectResults,
  type ChannelMode,
} from "../data/research";

export function SubjectResultChart() {
  const [subject, setSubject] = useState("ALL");
  const [metric, setMetric] = useState<"BA" | "AUC">("BA");
  const selected = subjectResults.find((item) => item.id === subject);
  const rows = (selected ? [selected] : subjectResults).map((item) => ({
    name: item.id,
    baseline: metric === "BA" ? item.baselineBA : item.baselineAUC,
    proposed: metric === "BA" ? item.proposedBA : item.proposedAUC,
  }));
  return (
    <div className="subject-results">
      <div className="comparison-filters compact">
        <label>
          피험자
          <select value={subject} onChange={(e) => setSubject(e.target.value)}>
            <option value="ALL">4인 전체 비교</option>
            {subjectResults.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} ({item.id})
              </option>
            ))}
          </select>
        </label>
        <label>
          지표
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as "BA" | "AUC")}
          >
            <option value="BA">균형정확도 BA</option>
            <option value="AUC">ROC-AUC</option>
          </select>
        </label>
      </div>
      <div className="result-chart">
        <ResponsiveContainer width="100%" height={330}>
          <BarChart
            data={rows}
            margin={{ top: 25, right: 20, left: 0, bottom: 8 }}
          >
            <CartesianGrid stroke="#DCE5EB" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fill: "#526574" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={metric === "BA" ? [50, 100] : [0.5, 1]}
              tickFormatter={(v) =>
                metric === "BA" ? `${v}%` : Number(v).toFixed(1)
              }
              tick={{ fill: "#526574", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              formatter={(value, name) => [
                metric === "BA" ? `${value}%` : Number(value).toFixed(4),
                name === "baseline" ? "16ch baseline" : "5~7ch proposed",
              ]}
              contentStyle={{
                background: "#fff",
                border: "1px solid #DCE5EB",
                borderRadius: 12,
              }}
            />
            <Bar
              dataKey="baseline"
              name="16ch baseline"
              fill="#9CAAB6"
              radius={[5, 5, 0, 0]}
            />
            <Bar
              dataKey="proposed"
              name="5~7ch proposed"
              fill="#39776F"
              radius={[5, 5, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {selected && (
        <div className="subject-detail">
          <div>
            <span>최적 구성</span>
            <strong>{selected.channels}</strong>
          </div>
          <div>
            <span>배포 모델</span>
            <strong>{selected.model}</strong>
          </div>
          <div>
            <span>검증 규모</span>
            <strong>
              {selected.sessions} · {selected.trials}회
            </strong>
          </div>
          <div>
            <span>잠재력 상한</span>
            <strong>
              {selected.ceilingBA}% BA · {selected.ceilingAUC.toFixed(4)} AUC
            </strong>
          </div>
        </div>
      )}
    </div>
  );
}
export function ResultChart() {
  const s = useBCI();
  return (
    <div className="result-chart">
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
            formatter={(v) => [`${v}%`, "Balanced accuracy"]}
          />
          <ReferenceLine
            y={54.5}
            stroke="#C76B67"
            strokeDasharray="5 5"
            label={{
              value: "영점조절 전 온라인 평균 54.50%",
              fill: "#9B4F4B",
              fontSize: 11,
              position: "insideTopLeft",
            }}
          />
          <Bar
            isAnimationActive={false}
            dataKey="ba"
            radius={[5, 5, 0, 0]}
            maxBarSize={86}
            label={{
              position: "top",
              fill: "#263746",
              formatter: (v: unknown) => `${v}%`,
            }}
          >
            {comparison.map((d) => (
              <Cell
                key={d.name}
                fill={
                  d.channels === (s.channelMode === "16ch" ? "16ch" : "low") &&
                  d.tta === s.ttaEnabled
                    ? "#39776F"
                    : "#9CAAB6"
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
          {sourceNote} 서로 다른 평가 조건을 직접 비교할 때는 세션 수와 트라이얼
          수를 함께 확인하세요.
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
          <span>TEST-TIME ADAPTATION</span>
          <strong>
            +12.3 <small>%p</small>
          </strong>
          <p>실시간 무감독 영점조절 독립 기여</p>
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
