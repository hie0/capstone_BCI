import type {
  BackendModel,
  BackendPrediction,
  BackendSession,
} from "./backend";

type ReplayAsset = { file: string; sha256: string; bytes: number };
type ReplaySession = BackendSession & { replays: Record<string, ReplayAsset> };
type ReplayManifest = { schema_version: number; sessions: ReplaySession[] };
export type RecordedReplay = {
  schema_version: number;
  participant_id: string;
  session_id: string;
  channel_mode: string;
  tta_enabled: boolean;
  total_trials: number;
  predictions: BackendPrediction[];
};
const replayCache = new Map<string, RecordedReplay>();
export class RecordedSessionUnavailableError extends Error {}
const rootUrl = () =>
  new URL(
    `${(import.meta as ImportMeta & { env: Record<string, string> }).env.BASE_URL}recorded-eeg/`,
    document.baseURI,
  );
function requireValue(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message);
}
function validModel(model: BackendModel) {
  return (
    model &&
    Array.isArray(model.active_channels) &&
    model.active_channels.length === model.n_channels
  );
}
async function loadManifest(signal: AbortSignal) {
  signal.throwIfAborted();
  const response = await fetch(new URL("manifest.json", rootUrl()), {
    signal,
    cache: "no-cache",
  });
  requireValue(response.ok, "Recorded EEG 재생 목록을 불러올 수 없습니다.");
  const data = (await response.json()) as ReplayManifest;
  requireValue(
    data.schema_version === 1 &&
      Array.isArray(data.sessions) &&
      data.sessions.length,
    "Recorded EEG 재생 목록 형식이 올바르지 않습니다.",
  );
  for (const s of data.sessions) {
    requireValue(
      s.participant_id &&
        s.session_id &&
        s.n_online_trials > 0 &&
        s.replays &&
        s.available_models,
      "EEG 세션 정보가 누락되었습니다.",
    );
    for (const [key, asset] of Object.entries(s.replays)) {
      requireValue(
        /^[a-z0-9_-]+\.json$/.test(asset.file) &&
          /^[a-f0-9]{64}$/.test(asset.sha256) &&
          validModel(s.available_models[key]),
        "EEG 파일 또는 채널 정보가 올바르지 않습니다.",
      );
    }
  }
  signal.throwIfAborted();
  return data;
}
export async function loadRecordedSessions(
  participant: string,
  signal: AbortSignal,
): Promise<BackendSession[]> {
  const manifest = await loadManifest(signal);
  signal.throwIfAborted();
  return manifest.sessions.filter((s) => s.participant_id === participant);
}
export async function loadRecordedReplay(
  participant: string,
  session: string,
  channel: string,
  tta: boolean,
  signal: AbortSignal,
): Promise<RecordedReplay> {
  // Revalidate the small manifest on every start/configuration load. Only
  // immutable, SHA-verified replay bodies may stay in the in-memory cache.
  // A deployment may change between the manifest and asset requests: refresh
  // once in that case, retaining all integrity checks on the second response.
  try {
    return await readRecordedReplay(participant, session, channel, tta, signal);
  } catch (error) {
    signal.throwIfAborted();
    if (error instanceof RecordedSessionUnavailableError) throw error;
    return readRecordedReplay(participant, session, channel, tta, signal, true);
  }
}

async function readRecordedReplay(
  participant: string,
  session: string,
  channel: string,
  tta: boolean,
  signal: AbortSignal,
  reload = false,
): Promise<RecordedReplay> {
  const manifest = await loadManifest(signal);
  const entry = manifest.sessions.find(
    (s) => s.participant_id === participant && s.session_id === session,
  );
  const key = `${channel}__tta_${tta ? "on" : "off"}`;
  if (!entry) throw new RecordedSessionUnavailableError("선택한 세션이 최신 재생 목록에서 제외되었습니다.");
  const asset = entry?.replays[key];
  requireValue(
    entry && asset,
    "선택한 EEG 세션·채널·TTA 재생 결과가 없습니다.",
  );
  signal.throwIfAborted();
  const cached = replayCache.get(asset.file);
  if (cached) return cached;
  const response = await fetch(new URL(asset.file, rootUrl()), {
    signal,
    cache: reload ? "reload" : "force-cache",
  });
  requireValue(response.ok, "Recorded EEG 추론 결과를 불러올 수 없습니다.");
  const raw = await response.text();
  const bytes = new TextEncoder().encode(raw);
  requireValue(
    bytes.byteLength === asset.bytes,
    "EEG 재생 파일의 크기가 일치하지 않습니다.",
  );
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  const sha = Array.from(new Uint8Array(hash), (n) =>
    n.toString(16).padStart(2, "0"),
  ).join("");
  requireValue(
    sha === asset.sha256,
    "EEG 재생 파일의 무결성 검증에 실패했습니다.",
  );
  const data = JSON.parse(raw) as RecordedReplay;
  requireValue(
    data.schema_version === 1 &&
      data.participant_id === participant &&
      data.session_id === session &&
      data.channel_mode === channel &&
      data.tta_enabled === tta &&
      data.total_trials === entry.n_online_trials &&
      data.predictions?.length === data.total_trials,
    "EEG 재생 설정 또는 Trial 수가 일치하지 않습니다.",
  );
  for (const [i, p] of data.predictions.entries()) {
    if (i === 0 && p.history_waveform) requireValue(
      p.active_channels.every(c => p.history_waveform?.[c]?.length === 500 && p.history_waveform[c].every(Number.isFinite)),
      "EEG 시작 전 파형이 올바르지 않습니다.",
    );
    requireValue(
      p.trial_id === i + 1 &&
        p.participant_id === participant &&
        p.session_id === session &&
        p.playback_source === "precomputed",
      "EEG Trial 순서 또는 세션이 일치하지 않습니다.",
    );
    requireValue(
      ["LEFT", "RIGHT"].includes(p.predicted_direction) &&
        (p.true_direction === null ||
          ["LEFT", "RIGHT"].includes(p.true_direction)),
      "EEG 예측 방향이 올바르지 않습니다.",
    );
    requireValue(
      [
        p.probability_left,
        p.probability_right,
        p.decision_score,
        p.latency_ms,
        p.raw_logit,
        p.calibrated_logit,
        p.timestamp,
      ].every(Number.isFinite) &&
        p.probability_right >= 0 &&
        p.probability_right <= 1 &&
        Math.abs(p.probability_left + p.probability_right - 1) < 1e-6,
      "EEG 예측 수치가 올바르지 않습니다.",
    );
    requireValue(
      typeof p.quality?.is_clean === "boolean" &&
        p.active_channels.join() ===
          entry.available_models[key].active_channels.join(),
      "EEG 품질 또는 활성 채널 정보가 올바르지 않습니다.",
    );
    requireValue(
      p.active_channels.every(
        (c) =>
          p.waveform?.[c]?.length === 250 &&
          p.waveform[c].every(Number.isFinite),
      ),
      "EEG 표시용 파형이 누락되었습니다.",
    );
  }
  signal.throwIfAborted();
  replayCache.set(asset.file, data);
  // Retain only a few recent configurations, rather than every EEG waveform.
  if (replayCache.size > 4)
    replayCache.delete(replayCache.keys().next().value!);
  return data;
}
