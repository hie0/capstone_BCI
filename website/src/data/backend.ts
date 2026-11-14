import type { Direction } from "./research";
export type BackendModel = {
  montage: string;
  active_channels: string[];
  n_channels: number;
  band: string;
  window: string;
};
export type BackendSession = {
  participant_id: string;
  session_id: string;
  n_online_trials: number;
  available_models: Record<string, BackendModel>;
};
export type BackendPrediction = {
  trial_id: number;
  timestamp: number;
  session_id: string;
  participant_id: string;
  predicted_direction: Direction;
  true_direction: Direction | null;
  model_name: string;
  model_id: string;
  active_channels: string[];
  probability_right: number;
  probability_left: number;
  decision_score: number;
  raw_logit: number;
  calibrated_logit: number;
  latency_ms: number;
  quality: {
    is_clean: boolean;
    status: string;
    eog_ptp_uv: number;
    threshold_uv: number;
  };
  waveform?: Record<string, number[]> | null;
};
export function selectedBackendModel(s: {
  backendSessions: BackendSession[];
  sessionId: string;
  channelMode: string;
  ttaEnabled: boolean;
  recordedLowChannel?: boolean;
}) {
  return s.backendSessions.find((x) => x.session_id === s.sessionId)
    ?.available_models[
    `${s.recordedLowChannel ? "low" : s.channelMode}__tta_${s.ttaEnabled ? "on" : "off"}`
  ];
}
// Production can supply a same-origin API reverse proxy or VITE_BCI_API_BASE.
const configured =
  (import.meta as ImportMeta & { env: Record<string, string> }).env
    .VITE_BCI_API_BASE ?? "";
export const apiUrl = (path: string) =>
  `${configured.replace(/\/$/, "")}${path}`;
export function eegSocketUrl() {
  const url = new URL(apiUrl("/ws/eeg"), window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}
