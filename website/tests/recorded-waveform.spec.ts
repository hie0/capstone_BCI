import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const root = new URL("../public/recorded-eeg/", import.meta.url);
const manifest = JSON.parse(
  readFileSync(new URL("manifest.json", root), "utf8"),
);
const session = manifest.sessions.find(
  (s: { participant_id: string }) => s.participant_id === "KGE",
);
const expected = JSON.parse(
  readFileSync(new URL(session.replays.low__tta_on.file, root), "utf8"),
).predictions[0];

test("recorded waveform scrolls within one trial using measured samples, freezes on pause and resumes", async ({
  page,
}) => {
  await page.goto("/#/simulation?app=game");
  const workerPromise = page.waitForEvent("worker");
  await page
    .getByRole("combobox", { name: "Input mode", exact: true })
    .selectOption("recorded");
  const worker = await workerPromise;
  await worker.evaluate(() => {
    const tracked = self as typeof self & {
      points: number[][];
      labels: { text: string; x: number; y: number }[];
      gaps: number[];
      previous: number;
    };
    tracked.points = [];
    tracked.labels = [];
    tracked.gaps = [];
    tracked.previous = 0;
    const proto = OffscreenCanvasRenderingContext2D.prototype;
    const fill = proto.fillRect,
      move = proto.moveTo,
      line = proto.lineTo;
    proto.fillRect = function (...args) {
      tracked.points = [];
      tracked.labels = [];
      return fill.apply(this, args);
    };
    proto.moveTo = function (x, y) {
      if (this.strokeStyle === "#527c98" && y > 0 && y < 48)
        tracked.points.push([x, y]);
      return move.call(this, x, y);
    };
    proto.lineTo = function (x, y) {
      if (this.strokeStyle === "#527c98" && y > 0 && y < 48)
        tracked.points.push([x, y]);
      return line.call(this, x, y);
    };
    const text = proto.fillText;
    proto.fillText = function (value, x, y, maxWidth) {
      const matrix = this.getTransform();
      tracked.labels.push({ text: value, x: matrix.a, y: matrix.d });
      if (maxWidth === undefined) return text.call(this, value, x, y);
      return text.call(this, value, x, y, maxWidth);
    };
    const raf = self.requestAnimationFrame.bind(self);
    self.requestAnimationFrame = (callback) =>
      raf((time) => {
        if (tracked.previous && time - tracked.previous < 100)
          tracked.gaps.push(time - tracked.previous);
        tracked.previous = time;
        callback(time);
      });
  });
  await expect(
    page.getByRole("combobox", { name: "Session", exact: true }),
  ).toHaveValue(session.session_id);
  const wave = page.getByRole("img", { name: "실제 EEG 파형" });
  const canvas = wave.locator("canvas");
  await page.waitForTimeout(100);
  const empty = await canvas.screenshot();
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=1");
  await page.waitForTimeout(250);
  const first = await canvas.screenshot();
  await page.waitForTimeout(350);
  const second = await canvas.screenshot();
  expect(second.equals(first)).toBe(false);
  expect(first.equals(empty)).toBe(false);
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=1");
  const diagnostics = await worker.evaluate(() => {
    const tracked = self as typeof self & {
      points: number[][];
      labels: { text: string; x: number; y: number }[];
      gaps: number[];
    };
    return {
      points: tracked.points,
      gaps: tracked.gaps,
      labels: tracked.labels,
    };
  });
  expect(diagnostics.labels.map((label) => label.text)).toEqual(
    expected.active_channels,
  );
  for (const label of diagnostics.labels) expect(label.x).toBe(label.y);
  const raw: number[] = expected.waveform[expected.active_channels[0]];
  const mean = raw.reduce((a, b) => a + b, 0) / raw.length;
  const scale = 18 / Math.max(1, ...raw.map((v) => Math.abs(v - mean)));
  const y = raw.map((v) => 24 - (v - mean) * scale);
  expect(diagnostics.points.length).toBeGreaterThan(100);
  expect(
    y.some((_, index) =>
      diagnostics.points.every(
        (point, i) => Math.abs(point[1] - y[index + i]) < 1e-6,
      ),
    ),
  ).toBe(true);
  const gaps = diagnostics.gaps.sort((a, b) => a - b);
  console.log(
    `Waveform worker median frame interval: ${gaps[Math.floor(gaps.length / 2)]?.toFixed(2)} ms`,
  );
  await page
    .getByRole("button", { name: "Pause", exact: true })
    .evaluate((e) => (e as HTMLButtonElement).click());
  await page.waitForTimeout(120);
  const paused = await canvas.screenshot();
  await page.waitForTimeout(350);
  expect((await canvas.screenshot()).equals(paused)).toBe(true);
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await page.waitForTimeout(350);
  expect((await canvas.screenshot()).equals(paused)).toBe(false);
  await page.screenshot({
    path: "../backend/local_cache/neuro-runner/scrolling-eeg.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=0");
  await expect
    .poll(async () => (await canvas.screenshot()).equals(empty))
    .toBe(true);
});

test("recorded waveform also scrolls when OffscreenCanvas is unavailable", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(
      HTMLCanvasElement.prototype,
      "transferControlToOffscreen",
      { value: undefined },
    );
  });
  await page.goto("/#/simulation?app=home");
  await page
    .getByRole("combobox", { name: "Input mode", exact: true })
    .selectOption("recorded");
  await expect(
    page.getByRole("combobox", { name: "Session", exact: true }),
  ).toHaveValue(session.session_id);
  await page
    .getByRole("button", { name: "실제 EEG 재생", exact: true })
    .click();
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=1");
  const canvas = page
    .getByRole("img", { name: "실제 EEG 파형" })
    .locator("canvas");
  const first = await canvas.screenshot();
  await page.waitForTimeout(250);
  expect((await canvas.screenshot()).equals(first)).toBe(false);
});
