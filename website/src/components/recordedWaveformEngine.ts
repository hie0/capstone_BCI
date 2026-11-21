export type WaveformMessage =
  | { type: "configure"; channels: string[] }
  | {
      type: "samples";
      samples: Record<string, number[]> | null | undefined;
      durationMs: number;
      version: number;
    }
  | { type: "playback"; playing: boolean; speed: number }
  | { type: "resize"; width: number; height: number; ratio: number };
type Segment = {
  start: number;
  end: number;
  rate: number;
  values: Record<string, number[]>;
};
const WINDOW = 125;
const GAP = 3;

// Display only: all y values come from measured, filtered EEG snippets. No
// procedural wave, repeated snippet or predicted sample is generated here.
export class RecordedWaveformEngine {
  private ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
  private channels: string[] = [];
  private segments: Segment[] = [];
  private cursor = 0;
  private end = 0;
  private playing = false;
  private speed = 1;
  private frame = 0;
  private last = 0;
  private version = -1;
  private width = 500;
  private height = 160;
  private ratio = 1;
  constructor(private canvas: HTMLCanvasElement | OffscreenCanvas) {
    this.ctx = canvas.getContext("2d", { alpha: false }) as
      CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
    if (!this.ctx) throw new Error("EEG Canvas context unavailable");
  }
  message(message: WaveformMessage) {
    if (message.type === "configure") {
      if (message.channels.join() !== this.channels.join()) {
        this.channels = message.channels;
        this.reset();
      }
    } else if (message.type === "resize") {
      this.width = message.width;
      this.height = message.height;
      this.ratio = message.ratio;
      this.canvas.width = Math.max(
        1,
        Math.round(message.width * message.ratio),
      );
      this.canvas.height = Math.max(
        1,
        Math.round(message.height * message.ratio),
      );
    } else if (message.type === "samples") {
      if (message.version === this.version) return;
      if (!message.samples) this.reset();
      else this.append(message.samples, message.durationMs);
      this.version = message.version;
    } else {
      this.playing = message.playing;
      this.speed = message.speed;
      if (this.playing && !this.frame) {
        this.last = performance.now();
        this.frame = requestAnimationFrame(this.animate);
      } else if (!this.playing) {
        cancelAnimationFrame(this.frame);
        this.frame = 0;
      }
    }
    this.draw();
  }
  private reset() {
    this.segments = [];
    this.cursor = 0;
    this.end = 0;
    this.version = -1;
  }
  private append(samples: Record<string, number[]>, durationMs: number) {
    const length = samples[this.channels[0]]?.length ?? 0;
    if (!length) return;
    const values: Record<string, number[]> = {};
    for (const channel of this.channels) {
      const raw = samples[channel];
      if (!raw?.length) continue;
      const mean = raw.reduce((sum, v) => sum + v, 0) / raw.length;
      const scale = 18 / Math.max(1, ...raw.map((v) => Math.abs(v - mean)));
      values[channel] = raw.map((v) => (v - mean) * scale);
    }
    const first = this.segments.length === 0;
    const start = first ? 0 : this.end + GAP;
    this.end = start + length;
    // Begin with a real, populated window, rather than an empty graph. The
    // rest of the snippet then flows into view without looping its samples.
    if (first) this.cursor = Math.min(WINDOW, length - 1);
    const active = this.segments.find((s) => s.end > this.cursor);
    if (active)
      active.rate = Math.max(active.rate, (active.end - this.cursor) / 350);
    this.segments.push({
      start,
      end: this.end,
      values,
      rate:
        (this.end - (first ? this.cursor : start - GAP)) /
        Math.max(1, durationMs),
    });
  }
  private animate = (now: number) => {
    let remaining = Math.min(100, now - this.last) * this.speed;
    this.last = now;
    while (remaining > 0) {
      const segment = this.segments.find((s) => s.end > this.cursor);
      if (!segment) break;
      const elapsed = Math.min(
        remaining,
        (segment.end - this.cursor) / segment.rate,
      );
      this.cursor = Math.min(segment.end, this.cursor + elapsed * segment.rate);
      remaining -= elapsed;
    }
    this.segments = this.segments.filter(
      (s) => s.end >= this.cursor - WINDOW - 1,
    );
    this.draw();
    this.frame = requestAnimationFrame(this.animate);
  };
  private draw() {
    const ctx = this.ctx;
    const height = Math.max(48, this.channels.length * 48);
    const labelEdge = Math.min(100, 36 * 500 / Math.max(1, this.width));
    ctx.setTransform(
      this.canvas.width / 500,
      0,
      0,
      this.canvas.height / height,
      0,
      0,
    );
    ctx.fillStyle = "#F8FBFD";
    ctx.fillRect(0, 0, 500, height);
    ctx.strokeStyle = "#DCE5EB";
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    for (let x = labelEdge; x <= 500; x += 25) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
    }
    for (let y = 0; y <= height; y += 24) {
      ctx.moveTo(labelEdge, y);
      ctx.lineTo(500, y);
    }
    ctx.stroke();
    ctx.save();
    ctx.beginPath();
    ctx.rect(labelEdge, 0, 500 - labelEdge, height);
    ctx.clip();
    ctx.lineWidth = 1.5;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    const left = this.cursor - WINDOW;
    for (const [row, channel] of this.channels.entries()) {
      ctx.strokeStyle = row % 2 ? "#8A79AF" : "#527C98";
      ctx.beginPath();
      let found = false;
      for (const segment of this.segments) {
        const values = segment.values[channel];
        if (!values || segment.end < left || segment.start > this.cursor)
          continue;
        // Include one measured point past each clipping edge so fractional
        // pixel movement is continuous, rather than advancing in whole samples.
        const first = Math.max(0, Math.floor(left - segment.start));
        const last = Math.min(
          values.length - 1,
          Math.ceil(this.cursor - segment.start),
        );
        for (let i = first; i <= last; i++) {
          const x = labelEdge + ((segment.start + i - left) * (500 - labelEdge)) / WINDOW;
          const y = 24 + row * 48 - values[i];
          if (i === first) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
          found = true;
        }
      }
      if (!found) {
        ctx.moveTo(labelEdge, 24 + row * 48);
        ctx.lineTo(500, 24 + row * 48);
      }
      ctx.stroke();
    }
    ctx.restore();
    // Text uses physical CSS pixels and a uniform DPR transform. The signal's
    // independently scaled x/y coordinate system must never stretch labels.
    ctx.save();
    ctx.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    const rowHeight = this.height / Math.max(1, this.channels.length);
    ctx.font = `${Math.min(11, Math.max(6, rowHeight * 0.5))}px system-ui, sans-serif`;
    ctx.fillStyle = "#697B89";
    ctx.textBaseline = "middle";
    for (const [row, channel] of this.channels.entries()) {
      ctx.fillText(channel, 6, (row + 0.5) * rowHeight);
    }
    ctx.restore();
  }
  destroy() {
    cancelAnimationFrame(this.frame);
    this.frame = 0;
  }
}
