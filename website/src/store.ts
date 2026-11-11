import { create } from "zustand";
import type { ChannelMode, Direction } from "./data/research";
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
  menu: number;
  control: boolean;
  pending: boolean;
  light: boolean;
  curtains: boolean;
  temperature: number;
  tv: number;
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
  temperature: 24,
  tv: 1,
  currentCommand: null,
  confidence: null,
  count: 0,
  history: [],
  isPlaying: false,
};
export const useBCI = create<State>((set) => ({
  ...initial,
  channelMode: "5ch",
  participantId: "demo-01",
  sessionId: "session-01",
  ttaEnabled: true,
  modelId: "low-channel-tta",
  inputMode: "manual",
  speed: 1,
  setSettings: (s) =>
    set((old) => ({ ...s, isPlaying: s.inputMode ? false : old.isPlaying })),
  command: (direction) =>
    set((s) => {
      const delta = direction === "RIGHT" ? 1 : -1;
      let next: Partial<State> = {};
      let message = "";
      if (!s.control) {
        const menu = (s.menu + delta + 4) % 4;
        next = { menu, pending: true };
        message = `${menus[menu]} 메뉴 탐색`;
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
            next = { tv: ((s.tv - 1 + delta + 5) % 5) + 1 };
            message = `TV 채널 ${next.tv}`;
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
  choose: (menu) => set({ menu, pending: true, control: false }),
  confirm: () => set({ control: true, pending: false }),
  back: () => set({ control: false, pending: false }),
  play: () => set({ isPlaying: true }),
  stop: () => set({ isPlaying: false }),
  reset: () => set({ ...initial, history: [] }),
}));
