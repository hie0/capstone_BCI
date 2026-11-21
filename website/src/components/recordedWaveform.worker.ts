import {
  RecordedWaveformEngine,
  type WaveformMessage,
} from "./recordedWaveformEngine";
let engine: RecordedWaveformEngine | undefined;
self.onmessage = (
  event: MessageEvent<
    WaveformMessage | { type: "init"; canvas: OffscreenCanvas }
  >,
) => {
  if (event.data.type === "init")
    engine = new RecordedWaveformEngine(event.data.canvas);
  else engine?.message(event.data);
};
