import type { PredictionRecord } from "./research";
export type EEGFrame = { timestamp: number; channels: Record<string, number> };
export interface ReplaySource {
  kind: "synthetic" | "recorded";
  predictions: PredictionRecord[];
  frames?: EEGFrame[];
  sampleRateHz?: number;
}
// Future CSV/JSON adapters should return ReplaySource and validate units, labels and channel ordering.
export function createDemoReplay(
  modelId: string,
  channelSet: string,
): ReplaySource {
  return {
    kind: "synthetic",
    predictions: Array.from({ length: 30 }, (_, i) => ({
      trialId: i + 1,
      timestamp: i * 2,
      trueLabel: null,
      predictedLabel: Math.sin(i * 2.7) > 0.1 ? "RIGHT" : "LEFT",
      score: 0.72 + ((i * 7) % 24) / 100,
      modelId,
      channelSet,
    })),
  };
}
