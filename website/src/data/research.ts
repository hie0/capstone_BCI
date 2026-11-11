export type Direction = "LEFT" | "RIGHT";
export type ChannelMode = "16ch" | "5ch" | "7ch";
export type PredictionRecord = {
  trialId: number;
  timestamp: number;
  trueLabel: Direction | null;
  predictedLabel: Direction;
  score?: number;
  modelId: string;
  channelSet: string;
};
export const core = ["F3", "F4", "C3", "Cz", "C4"];
export const electrodeNames = [
  "Fp1",
  "Fp2",
  "F7",
  "F3",
  "F4",
  "F8",
  "T7",
  "C3",
  "Cz",
  "C4",
  "T8",
  "P7",
  "Pz",
  "P8",
  "O1",
  "O2",
];
export const positions: Record<string, [number, number]> = {
  Fp1: [-0.35, -0.86],
  Fp2: [0.35, -0.86],
  F7: [-0.8, -0.48],
  F3: [-0.37, -0.43],
  F4: [0.37, -0.43],
  F8: [0.8, -0.48],
  T7: [-0.94, 0],
  C3: [-0.46, 0],
  Cz: [0, 0],
  C4: [0.46, 0],
  T8: [0.94, 0],
  P7: [-0.72, 0.51],
  Pz: [0, 0.51],
  P8: [0.72, 0.51],
  O1: [-0.34, 0.85],
  O2: [0.34, 0.85],
};
export const channelInfo = (name: string) =>
  name === "Cz"
    ? "정중앙 감각운동 영역 · 양측 운동 관련 정보를 보완합니다."
    : name === "C3"
      ? "좌측 감각운동 피질 부근 · 오른손 운동 상상과 관련된 신호를 탐색합니다."
      : name === "C4"
        ? "우측 감각운동 피질 부근 · 왼손 운동 상상과 관련된 신호를 탐색합니다."
        : ["F3", "F4"].includes(name)
          ? "전운동 관련 영역 · 운동 계획 정보를 보완하는 핵심 전극입니다."
          : name.startsWith("Fp")
            ? "전전두부 · 눈 깜빡임과 안구 움직임에 의한 잡음 영향을 받을 수 있습니다."
            : name.startsWith("O")
              ? "후두부 시각 관련 영역 · 본 연구의 감각운동 중심 구성에서는 제외합니다."
              : name.startsWith("T")
                ? "측두부 · 측두근 근전도 영향을 고려해야 합니다."
                : "전두·두정 주변 영역 · 보조 채널의 기여는 피험자별로 다를 수 있습니다.";
export const comparison = [
  { name: "16ch", ba: 69.28, channels: "16ch", tta: false },
  { name: "16ch + TTA", ba: 70.11, channels: "16ch", tta: true },
  { name: "Low-ch", ba: 72.09, channels: "low", tta: false },
  { name: "Low-ch + TTA", ba: 74.66, channels: "low", tta: true },
];
export const sourceNote =
  "출처: 사용자 제공 캡스톤 개발 요청서의 보고서 요약값. 온라인 50세션 사후 재분석 평균이며 현장 라이브 평가와 다른 조건입니다. 개별 피험자·5ch/7ch별 성능은 제공되지 않았습니다.";
