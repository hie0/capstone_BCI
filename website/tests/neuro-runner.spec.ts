import { test, expect, type Page } from "@playwright/test";

const lives = (page: Page) =>
  page
    .locator(".runner-hud > div")
    .filter({ has: page.locator("span", { hasText: /^Lives$/ }) })
    .locator("strong");
const pause = (page: Page) =>
  page
    .getByRole("button", { name: "Pause", exact: true })
    .evaluate((e) => (e as HTMLButtonElement).click());
async function openRecorded(page: Page, tta = true) {
  await page.goto("/#/simulation?app=game");
  await page
    .getByRole("combobox", { name: "Input mode", exact: true })
    .selectOption("recorded");
  await expect(
    page.getByRole("combobox", { name: "Session", exact: true }),
  ).toHaveValue("kge_online0928_01");
  const toggle = page.getByRole("switch", { name: "TTA", exact: true });
  if (((await toggle.getAttribute("aria-checked")) === "true") !== tta)
    await toggle.click();
}

test("runner pacing waits for approach and passing, and pause never advances the recorded trial", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript(() => {
    const tracked = window as Window & { runnerBufferCount: number };
    tracked.runnerBufferCount = 0;
    const original = WebGL2RenderingContext.prototype.createBuffer;
    WebGL2RenderingContext.prototype.createBuffer = function () {
      tracked.runnerBufferCount++;
      return original.call(this);
    };
  });
  await openRecorded(page);
  await expect(lives(page)).toHaveText("♥♥♥");
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=1");
  await page.waitForTimeout(1800);
  await expect(page.locator(".runner-canvas")).toHaveClass(/phase-running/);
  await expect(
    page.locator(".runner-monitor .command-history"),
  ).not.toContainText("Trial 1");
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=1");
  await pause(page);
  await expect(page.locator(".runner-canvas")).toHaveClass(/phase-paused/);
  await page
    .locator(".runner-canvas")
    .screenshot({
      path: "../backend/local_cache/neuro-runner/paused-approach.png",
    });
  await page.waitForTimeout(1200);
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=1");
  await expect(lives(page)).toHaveText("♥♥♥");
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.locator(".runner-monitor .command-history")).toContainText(
    "Trial 1",
    { timeout: 10000 },
  );
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=1");
  await expect(page.locator(".runner-canvas")).toHaveClass(/phase-passing/);
  await page
    .locator(".runner-canvas")
    .screenshot({ path: "../backend/local_cache/neuro-runner/passing.png" });
  const buffersBefore = await page.evaluate(() => (window as Window & { runnerBufferCount: number }).runnerBufferCount);
  expect(buffersBefore).toBeGreaterThan(0);
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=2");
  await expect(page.locator(".runner-canvas")).toHaveClass(/phase-running/);
  await pause(page);
  await page
    .locator(".runner-canvas")
    .screenshot({
      path: "../backend/local_cache/neuro-runner/new-obstacle-far.png",
    });
  const buffersAfter = await page.evaluate(() => (window as Window & { runnerBufferCount: number }).runnerBufferCount);
  expect(buffersAfter).toBe(buffersBefore);
  await expect(
    page.locator(".runner-monitor .command-history > div"),
  ).toHaveCount(1);
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(lives(page)).toHaveText("♥♥♥");
  await expect(page.locator(".runner-canvas")).toHaveClass(/phase-ready/);
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=0");
  expect(errors).toEqual([]);
});

test("runner lives uses three real recorded misclassifications, stops at zero and resets", async ({
  page,
}) => {
  // Existing export: first three KGE low/TTA-OFF trials are clean errors.
  // No prediction or target is mocked to force a game result.
  await openRecorded(page, false);
  await page
    .getByRole("combobox", { name: "Channel configuration", exact: true })
    .selectOption("16ch");
  await page
    .getByRole("combobox", { name: "Channel configuration", exact: true })
    .selectOption("low");
  await expect(
    page.getByRole("combobox", { name: "Channel configuration", exact: true }),
  ).toHaveValue("low");
  await page.getByRole("slider", { name: "Playback speed" }).fill("2");
  await expect(lives(page)).toHaveText("♥♥♥");
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(lives(page)).toHaveText("♥♥", { timeout: 10000 });
  await expect(lives(page)).toHaveText("♥", { timeout: 10000 });
  await expect(lives(page)).toHaveText("0", { timeout: 10000 });
  await expect(page.locator(".runner-canvas")).toHaveClass(/phase-game_over/, {
    timeout: 5000,
  });
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=3");
  await page.waitForTimeout(1500);
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=3");
  await expect(
    page.locator(".runner-monitor .command-history > div"),
  ).toHaveCount(3);
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(lives(page)).toHaveText("♥♥♥");
  await expect(page.locator(".runner-canvas")).toHaveClass(/phase-ready/);
});

test("runner manual mode also starts with three lives and each collision costs one", async ({
  page,
}) => {
  await page.goto("/#/simulation?app=game");
  await expect(lives(page)).toHaveText("♥♥♥");
  await page.getByRole("button", { name: "Start", exact: true }).click();
  for (let remaining = 2; remaining >= 0; remaining--) {
    await expect(page.locator(".runner-canvas")).toHaveClass(
      /phase-waiting_for_command/,
      { timeout: 12000 },
    );
    const target = await page
      .locator(".runner-monitor .monitor-stats > div")
      .filter({ has: page.locator("dt", { hasText: /^Target Direction$/ }) })
      .locator("dd")
      .textContent();
    await page
      .locator(".runner-controls")
      .getByRole("button", { name: target === "LEFT" ? /RIGHT/ : /LEFT/ })
      .click();
    await expect(lives(page)).toHaveText("♥".repeat(remaining) || "0");
  }
  await expect(page.locator(".runner-canvas")).toHaveClass(/phase-game_over/, {
    timeout: 5000,
  });
});
