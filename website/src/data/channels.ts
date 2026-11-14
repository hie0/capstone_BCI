export const fullMontage = [
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
export const pmCore = ["F3", "F4", "C3", "Cz", "C4"];
// Baseline specification supplied by the research team; no model artifact connected.
export const baseline16 = {
  id: "baseline-16-oas-ts-lr",
  name: "16ch OAS + Riemann TS + Logistic Regression",
  channels: fullMontage,
  sampleRateHz: 160,
  filter: { type: "Butterworth", order: 4, bandHz: [8, 30] },
  miWindowSeconds: [0.5, 3.5],
  covariance: "OAS (Oracle Approximating Shrinkage)",
  spdEigenvalueFloor: 1e-10,
  tangentMetric: "riemann",
  featureDimensions: 136,
  classifier: "StandardScaler() + LogisticRegression(C=0.5)",
  ttaEnabled: false,
  euclideanAlignment: false,
  logitCentering: false,
  validation: "LORO · 3개 Run 중 2개 학습 / 1개 평가",
  reportedLeakagePercent: 0,
  artifactConnected: false,
} as const;
export const channelConfigurations = {
  "16ch": {
    name: "16 Full Montage",
    channels: fullMontage,
    indices: fullMontage.map((_, i) => i),
    parameters: 136,
  },
  "5ch": {
    name: "5 Core Channels",
    channels: pmCore,
    indices: [3, 4, 7, 8, 9],
    parameters: 15,
  },
  "7ch": {
    name: "7 Extended Channels",
    channels: [...pmCore, "P7", "P8"],
    indices: [3, 4, 7, 8, 9, 11, 13],
    parameters: 28,
  },
};
export const participantModels = {
  WMJ: {
    name: "우민지",
    channelMode: "7ch",
    modelId: "wmj-reg-csp",
    modelName: "Regularized CSP + LDA",
  },
  KGE: {
    name: "강고은",
    channelMode: "5ch",
    modelId: "kge-oas-ts",
    modelName: "OAS + Riemann TS + SVC",
  },
  OYJ: {
    name: "오예진",
    channelMode: "5ch",
    modelId: "oyj-hybrid",
    modelName: "Hybrid TS+CSP + RBF SVC",
  },
  KHY: {
    name: "김희영",
    channelMode: "7ch",
    modelId: "khy-spd-ts",
    modelName: "Ensure-SPD + TS + sLDA",
  },
} as const;
export type ParticipantId = keyof typeof participantModels;
export const configuredChannels = (mode: keyof typeof channelConfigurations) =>
  channelConfigurations[mode].channels;
