// Historical benchmarks only. Authoritative source: user-provided
// 4인_f1스코어_요약.md, §1.②/⑥, §2, §3. Never used for live predictions.
export type BenchmarkParticipant = "KGE" | "KHY" | "OYJ" | "WMJ" | "ALL";
export const benchmarkConditions = [
  { key: "baseline", name: "16ch Baseline", color: "#A6B4C0" },
  { key: "fullTta", name: "16ch + TTA", color: "#708CA1" },
  { key: "lowOnly", name: "Low Channel Only", color: "#A2C6BC" },
  { key: "lowTta", name: "Low Channel + TTA", color: "#39776F" },
] as const;
export const comparisonConditions = [
  benchmarkConditions[0],
  benchmarkConditions[3],
] as const;
export type ComparisonRow = {
  participant: BenchmarkParticipant;
  baseline: number;
  lowTta: number;
};
export type BenchmarkCondition = (typeof benchmarkConditions)[number]["key"];
export type BenchmarkRow = {
  participant: BenchmarkParticipant;
  baseline: number;
  fullTta: number;
  lowOnly: number;
  lowTta: number;
};
const row = (
  participant: BenchmarkParticipant,
  baseline: number,
  fullTta: number,
  lowOnly: number,
  lowTta: number,
): BenchmarkRow => ({ participant, baseline, fullTta, lowOnly, lowTta });

export const losoMacroF1: BenchmarkRow[] = [
  row("KGE", 63.95, 69.0, 68.81, 71.09),
  row("KHY", 57.79, 59.58, 60.61, 64.91),
  row("OYJ", 64.97, 68.98, 58.76, 67.53),
  row("WMJ", 66.3, 80.66, 74.95, 83.33),
  row("ALL", 63.25, 69.55, 65.78, 71.72),
];
export const onlineMacroF1: BenchmarkRow[] = [
  row("KGE", 65.59, 68.98, 68.23, 72.62),
  row("KHY", 59.44, 62.85, 62.35, 66.51),
  row("OYJ", 74.78, 74.6, 77.94, 81.45),
  row("WMJ", 70.03, 72.27, 75.92, 76.35),
  row("ALL", 67.46, 69.67, 71.11, 74.23),
];
// Poster BA (different from the older live-vs-adjusted cohort series retained in research.ts).
export const onlinePosterBA: BenchmarkRow[] = [
  row("KGE", 67.55, 69.27, 69.84, 72.83),
  row("KHY", 62.18, 63.32, 63.98, 67.23),
  row("OYJ", 75.11, 75.17, 78.5, 81.83),
  row("WMJ", 72.26, 72.68, 76.03, 76.77),
  row("ALL", 69.28, 70.11, 72.09, 74.66),
];
export const externalMacroF1 = [
  { condition: "16ch Baseline", mean: 59.33, sd: 14.73 },
  { condition: "16ch + TTA", mean: 60.76, sd: 15.18 },
  { condition: "Low Channel Only", mean: 64.37, sd: 15.21 },
  { condition: "Low Channel + TTA", mean: 65.77, sd: 15.86 },
] as const;
export const benchmarkStatistics = {
  online: {
    unit: "50 sessions",
    n: 50,
    sessionMeanDelta: 6.79,
    pairedT: "1.90 × 10⁻⁸",
    wilcoxon: "2.85 × 10⁻⁷",
  },
  external: {
    unit: "100 participants",
    n: 100,
    improved: 74,
    delta: 6.44,
    pairedT: "8.33 × 10⁻⁸",
    wilcoxon: "2.60 × 10⁻⁷",
  },
} as const;
export const losoF1Average = losoMacroF1[4];
export const onlineF1Average = onlineMacroF1[4];
export const percentagePointDelta = (n: number) =>
  `${n >= 0 ? "+" : ""}${n.toFixed(2)}%p`;
