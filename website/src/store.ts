import { create } from "zustand";
import type { ChannelMode, Direction } from "./data/research";
import { participantModels, type ParticipantId } from "./data/channels";
import type { BackendPrediction, BackendSession } from "./data/backend";
export const menus = [
  "Lighting",
  "Curtains",
  "Temperature",
  "Television",
] as const;
type Settings = {
  channelMode: ChannelMode;
  participantId: string;
  sessionId: string;
  ttaEnabled: boolean;
  modelId: string;
  inputMode: "manual" | "synthetic" | "recorded";
  speed: number;
};
type Entry = {
  id: number;
  direction: Direction;
  message: string;
  time: string;
};
type State = Settings & {
  backendSessions: BackendSession[];
  backendError: string | null;
  backendStatus: string;
  recordedPrediction: BackendPrediction | null;
  recordedTimeline: BackendPrediction[];
  recordedCursor: number;
  setBackend: (
    data: Partial<
      Pick<State, "backendSessions" | "backendError" | "backendStatus">
    >,
  ) => void;
  receivePrediction: (
    prediction: BackendPrediction,
    controlDevices: boolean,
  ) => void;
  seekRecorded: (index: number) => void;
  menu: number;
  control: boolean;
  pending: boolean;
  light: boolean;
  curtains: boolean;
  temperature: number;
  tv: boolean;
  currentCommand: Direction | null;
  confidence: number | null;
  count: number;
  history: Entry[];
  isPlaying: boolean;
  setSettings: (s: Partial<Settings>) => void;
  command: (d: Direction) => void;
  choose: (n: number) => void;
  confirm: () => void;
  back: () => void;
  play: () => void;
  stop: () => void;
  reset: () => void;
};
const initial = {
  menu: 0,
  control: false,
  pending: false,
  light: true,
  curtains: true,
  temperature: 22,
  tv: false,
  currentCommand: null,
  confidence: null,
  count: 0,
  history: [],
  isPlaying: false,
};
export const useBCI = create<State>((set, get) => ({
  ...initial,
  backendSessions: [],
  backendError: null,
  backendStatus: "미연결",
  recordedPrediction: null,
  recordedTimeline: [],
  recordedCursor: 0,
  setBackend: (data) => set(data),
  receivePrediction: (prediction, controlDevices) => {
    if (controlDevices && prediction.quality.is_clean)
      get().command(prediction.predicted_direction);
    set((s) => ({
      recordedPrediction: prediction,
      recordedTimeline: [
        ...s.recordedTimeline.filter((p) => p.trial_id !== prediction.trial_id),
        prediction,
      ].sort((a, b) => a.trial_id - b.trial_id),
      recordedCursor: prediction.trial_id,
      currentCommand: prediction.predicted_direction,
      confidence: Math.round(
        100 *
          Math.max(prediction.probability_left, prediction.probability_right),
      ),
      backendStatus: prediction.quality.is_clean
        ? "실제 EEG 추론 중"
        : "Artifact · 명령 보류",
    }));
  },
  seekRecorded: (index) =>
    set((s) => ({
      isPlaying: false,
      recordedCursor: index,
      recordedPrediction:
        s.recordedTimeline.find((p) => p.trial_id === index + 1) ?? null,
    })),
  channelMode: "5ch",
  participantId: "KGE",
  sessionId: "session-01",
  ttaEnabled: true,
  modelId: participantModels.KGE.modelId,
  inputMode: "manual",
  speed: 1,
  setSettings: (s) =>
    set((old) => {
      const profile =
        participantModels[
          (s.participantId ?? old.participantId) as ParticipantId
        ];
      if (!profile) return {};
      const mode = s.participantId
        ? profile.channelMode
        : (s.channelMode ?? old.channelMode);
      return {
        ...s,
        sessionId:
          s.inputMode && s.inputMode !== "recorded"
            ? "session-01"
            : (s.sessionId ?? old.sessionId),
        channelMode: mode,
        modelId:
          (s.inputMode ?? old.inputMode) === "recorded"
            ? "online-calib20"
            : mode === profile.channelMode
              ? profile.modelId
              : "visualization-only",
        ...(s.inputMode ||
        s.participantId ||
        s.sessionId ||
        s.channelMode ||
        s.ttaEnabled !== undefined
          ? {
              isPlaying: false,
              recordedPrediction: null,
              recordedTimeline: [],
              recordedCursor: 0,
              confidence: null,
              currentCommand: null,
              backendError: null,
            }
          : {}),
      };
    }),
  command: (direction) =>
    set((s) => {
      const delta = direction === "RIGHT" ? 1 : -1;
      let next: Partial<State> = {};
      let message = "";
      if (!s.control) {
        const menu = (s.menu + delta + 4) % 4;
        next = { menu, pending: false, control: true };
        message = `${menus[menu]} 메뉴 선택`;
      } else {
        switch (s.menu) {
          case 0:
            next = { light: direction === "RIGHT" };
            message = `조명 ${direction === "RIGHT" ? "ON" : "OFF"}`;
            break;
          case 1:
            next = { curtains: direction === "RIGHT" };
            message = `커튼 ${direction === "RIGHT" ? "열림" : "닫힘"}`;
            break;
          case 2:
            next = {
              temperature: Math.max(16, Math.min(30, s.temperature + delta)),
            };
            message = `온도 ${next.temperature}°C`;
            break;
          case 3:
            next = { tv: direction === "RIGHT" };
            message = `TV 전원 ${direction === "RIGHT" ? "ON" : "OFF"}`;
        }
      }
      return {
        ...next,
        currentCommand: direction,
        confidence:
          s.inputMode === "synthetic"
            ? Math.round(72 + Math.random() * 24)
            : null,
        count: s.count + 1,
        history: [
          {
            id: s.count + 1,
            direction,
            message,
            time: new Date().toLocaleTimeString("ko-KR", { hour12: false }),
          },
          ...s.history,
        ].slice(0, 50),
      };
    }),
  choose: (menu) => set({ menu, pending: false, control: true }),
  confirm: () => set({ control: true, pending: false }),
  back: () => set({ control: false, pending: false }),
  play: () =>
    set((s) => ({
      isPlaying: true,
      ...(s.inputMode === "recorded" &&
      s.recordedCursor >=
        (s.backendSessions.find((x) => x.session_id === s.sessionId)
          ?.n_online_trials ?? Infinity)
        ? { recordedCursor: 0, recordedPrediction: null, recordedTimeline: [] }
        : {}),
    })),
  stop: () =>
    set((s) => ({
      isPlaying: false,
      ...(s.inputMode === "recorded" && s.backendStatus === "실제 EEG 추론 중"
        ? { backendStatus: "일시정지" }
        : {}),
    })),
  reset: () =>
    set({
      ...initial,
      history: [],
      recordedPrediction: null,
      recordedTimeline: [],
      recordedCursor: 0,
      backendError: null,
    }),
}));
