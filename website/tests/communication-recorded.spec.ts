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
  await expect(page.locator(".left-gauge-label")).toContainText("60%");
  await expect(page.getByTestId("quality-gate")).toHaveText(
    predictions[4].quality.status,
  );
  await expect(page.locator(".comm-speech-window")).toContainText(sentence, {
    timeout: 20000,
  });
  await expect(
    page.getByRole("button", { name: "다음 문장 선택", exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=13");
  await page.waitForTimeout(1200);
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=13");
  expect(
    await page.evaluate(() => (window as Window & { spoken: string[] }).spoken),
  ).toEqual([sentence]);
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
