import { useEffect, useRef } from "react";
import {
  RecordedWaveformEngine,
  type WaveformMessage,
} from "./recordedWaveformEngine";

export function RecordedWaveform({
  channels,
  samples,
  playing,
  speed,
  durationMs,
  continuous = false,
  history,
}: {
  channels: string[];
  samples?: Record<string, number[]> | null;
  playing: boolean;
  speed: number;
  durationMs: number;
  continuous?: boolean;
  history?: Record<string, number[]> | null;
}) {
  const host = useRef<HTMLDivElement>(null);
  const driver = useRef<{
    send: (message: WaveformMessage) => void;
    destroy: () => void;
  } | null>(null);
  const latest = useRef({ channels, samples, playing, speed, durationMs, continuous, history });
  latest.current = { channels, samples, playing, speed, durationMs, continuous, history };
  const channelKey = channels.join(",");
  const revision = useRef(0);
  const previous = useRef<{ samples: typeof samples; channels: string; history: typeof history } | null>(
    null,
  );
  if (
    previous.current?.samples !== samples ||
    previous.current?.channels !== channelKey || previous.current?.history !== history
  ) {
    revision.current++;
    previous.current = { samples, channels: channelKey, history };
  }
  useEffect(() => {
    const element = host.current!;
    const createCanvas = () => {
      const canvas = document.createElement("canvas");
      canvas.style.cssText = "display:block;width:100%;height:100%";
      canvas.setAttribute("aria-hidden", "true");
      element.replaceChildren(canvas);
      return canvas;
    };
    let canvas = createCanvas();
    const resize = () => {
      const rect = element.getBoundingClientRect();
      driver.current?.send({
        type: "resize",
        width: rect.width,
        height: rect.height,
        ratio: Math.min(2, devicePixelRatio || 1),
      });
    };
    const initialize = () => {
      const s = latest.current;
      driver.current?.send({ type: "configure", channels: s.channels, continuous: s.continuous });
      driver.current?.send({
        type: "playback",
        playing: s.playing,
        speed: s.speed,
      });
      driver.current?.send({
        type: "samples",
        samples: s.samples,
        history: s.history,
        durationMs: s.durationMs,
        version: revision.current,
      });
      resize();
    };
    const fallback = () => {
      driver.current?.destroy();
      canvas = createCanvas();
      const engine = new RecordedWaveformEngine(canvas);
      driver.current = {
        send: (message) => engine.message(message),
        destroy: () => engine.destroy(),
      };
      initialize();
    };
    try {
      if (
        typeof Worker === "undefined" ||
        !canvas.transferControlToOffscreen ||
        typeof OffscreenCanvas === "undefined"
      )
        throw new Error("OffscreenCanvas unavailable");
      const worker = new Worker(
        new URL("./recordedWaveform.worker.ts", import.meta.url),
        { type: "module" },
      );
      driver.current = {
        send: (message) => worker.postMessage(message),
        destroy: () => {
          worker.onerror = null;
          worker.terminate();
        },
      };
      worker.onerror = (event) => {
        event.preventDefault();
        fallback();
      };
      const offscreen = canvas.transferControlToOffscreen();
      worker.postMessage({ type: "init", canvas: offscreen }, [offscreen]);
      initialize();
    } catch {
      fallback();
    }
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    return () => {
      observer.disconnect();
      driver.current?.destroy();
      driver.current = null;
      element.replaceChildren();
    };
  }, []);
  useEffect(() => {
    driver.current?.send({ type: "configure", channels, continuous });
  }, [channelKey, continuous]);
  useEffect(() => {
    driver.current?.send({
      type: "samples",
      samples,
      history,
      durationMs,
      version: revision.current,
    });
  }, [samples, channelKey, continuous, history]);
  useEffect(() => {
    driver.current?.send({ type: "playback", playing, speed });
  }, [playing, speed]);
  return (
    <div
      ref={host}
      className="recorded-waveform"
      role="img"
      aria-label="실제 EEG 파형"
      data-channels={channelKey}
      data-history-samples={continuous ? history?.[channels[0]]?.length ?? 0 : 0}
    />
  );
}
