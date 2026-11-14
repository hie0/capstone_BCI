export type Direction = "LEFT" | "RIGHT";
export type ChannelMode = "16ch" | "5ch" | "7ch";
export const channelReduction = {
  "5ch": 68.75,
  "7ch": 56.25,
} as const;
export type PredictionRecord = {
  trialId: number;
  timestamp: number;
  trueLabel: Direction | null;
  predictedLabel: Direction;
  score?: number;
  modelId: string;
  channelSet: string;
};
export { pmCore as core, fullMontage as electrodeNames } from "./channels";
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
  name === "P7" || name === "P8"
    ? `${name === "P7" ? "Left" : "Right"} Parietal Region · 감각운동 관련 공간적 EEG 정보 확장, 두정엽 신호를 활용한 개인별 특징 추출. WMJ·KHY 7ch_PM에서 공통 5채널을 확장하는 추가 전극입니다.`
    : name === "Cz"
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
  {
    name: "18세션",
    trials: 1440,
    baselineBA: 53.9,
    adjustedBA: 75.7,
    improvement: 21.8,
    significance: "p = 0.020",
  },
  {
    name: "32세션",
    trials: 2470,
    baselineBA: 54.8,
    adjustedBA: 74.15,
    improvement: 19.35,
    significance: "p < 10⁻¹²",
  },
  {
    name: "50세션",
    trials: 3910,
    baselineBA: 54.5,
    adjustedBA: 74.71,
    improvement: 20.21,
    significance: "p < 10⁻¹⁷",
  },
];
export type SubjectResult = {
  id: "WMJ" | "KGE" | "OYJ" | "KHY";
  name: string;
  sessions: string;
  trials: number;
  channels: "5ch" | "7ch";
  model: string;
  baselineBA: number;
  proposedBA: number;
  baselineAUC: number;
  proposedAUC: number;
};
export const subjectResults: SubjectResult[] = [
  {
    id: "KGE",
    name: "강고은",
    sessions: "4개 런",
    trials: 320,
    channels: "5ch",
    model: "Riemann TS + SVC",
    baselineBA: 70,
    proposedBA: 78.43,
    baselineAUC: 0.7512,
    proposedAUC: 0.8252,
  },
  {
    id: "KHY",
    name: "김희영",
    sessions: "4개 런",
    trials: 320,
    channels: "7ch",
    model: "Ensure-SPD + TS",
    baselineBA: 58,
    proposedBA: 66.65,
    baselineAUC: 0.611,
    proposedAUC: 0.7003,
  },
  {
    id: "OYJ",
    name: "오예진",
    sessions: "5개 런",
    trials: 400,
    channels: "5ch",
    model: "Hybrid TS+CSP",
    baselineBA: 68,
    proposedBA: 75.82,
    baselineAUC: 0.742,
    proposedAUC: 0.8123,
  },
  {
    id: "WMJ",
    name: "우민지",
    sessions: "5개 런",
    trials: 400,
    channels: "7ch",
    model: "Reg-CSP + LDA",
    baselineBA: 77.1,
    proposedBA: 83.33,
    baselineAUC: 0.8512,
    proposedAUC: 0.9022,
  },
];
export const sourceNote =
  "출처: 최종 연구발표자료 p.12(4인 LOSO) 및 p.16(실전 온라인 50세션). LOSO와 온라인 검증은 평가 조건이 다른 별도 결과입니다.";
