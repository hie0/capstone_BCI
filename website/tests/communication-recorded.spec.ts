import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const root = new URL("../public/recorded-eeg/", import.meta.url);
const manifest = JSON.parse(
  readFileSync(new URL("manifest.json", root), "utf8"),
);
const session = manifest.sessions.find(
  (s: { session_id: string }) => s.session_id === "wmj_online0929_01",
);
const predictions = JSON.parse(
  readFileSync(new URL(session.replays.low__tta_off.file, root), "utf8"),
).predictions;
const sentence = "목이 마릅니다. 시원한 물 한 잔만 주세요.";
const recordedSentence = "실내 공기가 너무 춥거나 덥습니다. 온도 조절 부탁드립니다.";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const tracked = window as Window & { spoken: string[] };
    tracked.spoken = [];
    Object.defineProperty(window, "speechSynthesis", {
      configurable: true,
      value: {
        cancel() {},
        getVoices() {
          return [];
        },
        onvoiceschanged: null,
        speak(utterance: SpeechSynthesisUtterance) {
          tracked.spoken.push(utterance.text);
        },
      },
    });
  });
});

test("communication follows actual predictions, rejects artifacts, pauses pending selections and speaks the recorded path", async ({
  page,
}) => {
  const forbidden: string[] = [];
  page.on("request", (request) => {
    if (/\/(api|ws)\//.test(request.url())) forbidden.push(request.url());
  });
  page.on("websocket", (ws) => forbidden.push(ws.url()));
  await page.goto("/#/simulation?app=communication");
  await page
    .getByRole("combobox", { name: "Input mode", exact: true })
    .selectOption("recorded");
  await page
    .getByRole("combobox", { name: "Participant", exact: true })
    .selectOption("WMJ");
  await expect(
    page.getByRole("combobox", { name: "Session", exact: true }),
  ).toHaveValue(/^wmj_online/);
  await page
    .getByRole("combobox", { name: "Session", exact: true })
    .selectOption(session.session_id);
  await page.getByRole("switch", { name: "TTA", exact: true }).click();
  await page.getByRole("slider", { name: "Playback speed" }).fill("2");
  await expect(page.locator(".option-card.left-card")).toBeDisabled();
  await expect(page.locator(".wave-box .meta-val.status-on")).toHaveCount(0);
  // Pause immediately when the first 80% decision is pending, before its 600ms
  // confirmation timer. No fake EEG or modified model probabilities are used.
  await page.evaluate(() => {
    const gauge = document.querySelector(".left-gauge-label")!;
    const observer = new MutationObserver(() => {
      if (gauge.textContent?.includes("80%")) {
        const button = [
          ...document.querySelectorAll(".communication-playback button"),
        ].find((b) => b.textContent?.includes("일시정지")) as HTMLButtonElement;
        if (button) {
          button.click();
          observer.disconnect();
        }
      }
    });
    observer.observe(gauge, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  });
  await page
    .getByRole("button", { name: "실제 EEG 재생", exact: true })
    .click();
  await expect(page.getByTestId("decision-score")).toHaveText(
    predictions[0].decision_score.toFixed(4),
  );
  expect(predictions[0].predicted_direction).not.toBe(
    predictions[0].true_direction,
  );
  await expect(page.getByRole("img", { name: "실제 EEG 파형" })).toBeVisible();
  await expect(
    page.getByText("Synthetic EEG Demo · μV illustrative", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "실제 EEG 재생", exact: true }),
  ).toBeVisible({ timeout: 10000 });
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=3");
  await page.waitForTimeout(800);
  await expect(page.locator(".left-gauge-label")).toContainText("80%");
  await expect(page.locator(".left-card .card-label")).toHaveText(
    "신체적·생리적 욕구",
  );
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=3");
  await page
    .getByRole("button", { name: "실제 EEG 재생", exact: true })
    .click();
  await expect(page.locator(".left-card .card-label")).toHaveText(
    "음료 및 식사 (식음)",
  );
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=5", {
    timeout: 10000,
  });
  expect(predictions[4].quality.is_clean).toBe(false);
  await expect(page.locator(".left-gauge-label")).toContainText("40%");
  await expect(page.getByTestId("quality-gate")).toHaveText(
    predictions[4].quality.status,
  );
  const waveform = page.getByRole("img", { name: "실제 EEG 파형" }).locator("canvas");
  const rejectedFrame = await waveform.screenshot();
  await page.waitForTimeout(150);
  expect((await waveform.screenshot()).equals(rejectedFrame)).toBe(false);
  await expect(page.locator(".comm-speech-window")).toContainText(recordedSentence, {
    timeout: 20000,
  });
  await expect(
    page.getByRole("button", { name: "다음 문장 선택", exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=15");
  await page.waitForTimeout(1200);
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=15");
  expect(
    await page.evaluate(() => (window as Window & { spoken: string[] }).spoken),
  ).toEqual([recordedSentence]);
  await page.screenshot({
    path: "../backend/local_cache/communication-recorded-1440.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "처음으로", exact: true }).click();
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=0");
  await expect(page.locator(".left-gauge-label")).toContainText("50%");
  await expect(page.locator(".left-card .card-label")).toHaveText(
    "신체적·생리적 욕구",
  );
  await page.getByRole("button", { name: /SMART HOME 제어/ }).click();
  await expect(page.getByTestId("command-count")).toHaveText("000");
  expect(forbidden).toEqual([]);
});

test("communication manual cards keep the three-step selection and speech behavior", async ({
  page,
}) => {
  await page.goto("/#/simulation?app=communication");
  for (const next of [
    "음료 및 식사 (식음)",
    "목말라요. 물을 주세요.",
    sentence,
  ]) {
    for (let i = 0; i < 3; i++)
      await page.locator(".option-card.left-card").click();
    if (next === sentence)
      await expect(page.locator(".comm-speech-window")).toContainText(sentence);
    else await expect(page.locator(".left-card .card-label")).toHaveText(next);
  }
  expect(
    await page.evaluate(() => (window as Window & { spoken: string[] }).spoken),
  ).toEqual([sentence]);
  await page.getByRole("button", { name: "이전 단계", exact: true }).click();
  await expect(page.locator(".left-card .card-label")).toHaveText(
    "음료 및 식사 (식음)",
  );
});

test("communication demo waveform keeps moving while idle and between tree selections", async ({ page }) => {
  await page.goto("/#/simulation?app=communication");
  await page.getByRole("combobox", { name: "Input mode", exact: true }).selectOption("manual");
  const signal = page.locator('.wave-box svg[aria-label="합성 EEG 파형"] path[stroke="#527C98"]').first();
  const initial = await signal.getAttribute("d");
  await expect.poll(() => signal.getAttribute("d")).not.toBe(initial);
  for (let i = 0; i < 3; i++) await page.locator(".option-card.left-card").click();
  await expect(page.locator(".left-card .card-label")).toHaveText("음료 및 식사 (식음)");
  await expect(page.locator(".brain-box .suite-badge")).toHaveText("LEFT 활성");
  const waiting = await signal.getAttribute("d");
  await expect.poll(() => signal.getAttribute("d")).not.toBe(waiting);
});

test("communication recorded waveform scrolls slowly without catch-up bursts and freezes only on pause", async ({ page }) => {
  await page.goto("/#/simulation?app=communication");
  const workerPromise = page.waitForEvent("worker");
  await page.getByRole("combobox", { name: "Input mode", exact: true }).selectOption("recorded");
  const worker = await workerPromise;
  await page.getByRole("combobox", { name: "Participant", exact: true }).selectOption("WMJ");
  await expect(page.getByRole("combobox", { name: "Session", exact: true })).toHaveValue(/^wmj_online/);
  await page.getByRole("combobox", { name: "Session", exact: true }).selectOption(session.session_id);
  await page.getByRole("switch", { name: "TTA", exact: true }).click();
  const raw: number[] = predictions[0].history_waveform[predictions[0].active_channels[0]];
  const mean = raw.reduce((a, b) => a + b, 0) / raw.length;
  const index = raw.findIndex((v, i) => i >= 300 && i <= 400 && raw.filter(x => x === v).length === 1);
  expect(index).toBeGreaterThanOrEqual(300);
  const y = 24 - (raw[index] - mean) * 18 / Math.max(1, ...raw.map(v => Math.abs(v - mean)));
  await worker.evaluate(({ target }) => {
    const tracked = self as typeof self & { positions: { x: number; y: number; t: number }[]; profile: number[] };
    tracked.positions = []; tracked.profile = [];
    const proto = OffscreenCanvasRenderingContext2D.prototype;
    const fill = proto.fillRect, move = proto.moveTo, line = proto.lineTo;
    proto.fillRect = function (...args) { tracked.profile = []; return fill.apply(this, args); };
    const capture = (ctx: OffscreenCanvasRenderingContext2D, x: number, y: number) => {
      if (ctx.strokeStyle === "#527c98" && y > 0 && y < 48) {
        tracked.profile.push(x);
        if (Math.abs(y - target) < 1e-6) tracked.positions.push({ x, y, t: performance.now() });
      }
    };
    proto.moveTo = function (x, y) { capture(this, x, y); return move.call(this, x, y); };
    proto.lineTo = function (x, y) { capture(this, x, y); return line.call(this, x, y); };
  }, { target: y });
  const wave = page.getByRole("img", { name: "실제 EEG 파형" });
  await expect(wave).toHaveAttribute("data-history-samples", "500");
  await page.setViewportSize({ width: 1441, height: 1100 });
  await expect.poll(() => worker.evaluate(() => {
    const xs = (self as typeof self & { profile: number[] }).profile;
    return Math.max(...xs) - Math.min(...xs);
  })).toBeGreaterThan(400);
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=0");
  await page.waitForTimeout(100);
  const preview = await wave.locator("canvas").screenshot();
  await page.waitForTimeout(150);
  expect((await wave.locator("canvas").screenshot()).equals(preview)).toBe(true);
  await page.screenshot({ path: "../backend/local_cache/communication-prefilled.png", fullPage: true });
  await worker.evaluate(() => { (self as typeof self & { positions: unknown[] }).positions = []; });
  await page.getByRole("button", { name: "실제 EEG 재생", exact: true }).click();
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=2");
  await page.waitForTimeout(350);
  const points = await worker.evaluate(() => (self as typeof self & { positions: { x: number; y: number; t: number }[] }).positions);
  const measured = points.filter(p => Math.abs(p.y - y) < 1e-6);
  // Measure over 200ms windows: per-frame performance.now() can jitter relative
  // to the worker's rAF timestamp when Chrome dispatches messages or does GC.
  const velocities = measured.flatMap((p, i) => {
    const prior = measured.slice(0, i).findLast(q => p.t - q.t >= 200);
    return prior ? [(prior.x - p.x) / (p.t - prior.t)] : [];
  });
  expect(velocities.length).toBeGreaterThan(30);
  expect(Math.max(...velocities)).toBeLessThan(0.16);
  expect(velocities.filter(v => v > 0.04).length / velocities.length).toBeGreaterThan(0.9);
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  const canvas = page.getByRole("img", { name: "실제 EEG 파형" }).locator("canvas");
  await page.waitForTimeout(120);
  const paused = await canvas.screenshot();
  await page.waitForTimeout(200);
  expect((await canvas.screenshot()).equals(paused)).toBe(true);
  await page.getByRole("button", { name: "실제 EEG 재생", exact: true }).click();
  await page.waitForTimeout(200);
  expect((await canvas.screenshot()).equals(paused)).toBe(false);
});
