import { test, expect } from "@playwright/test";

test("Phase4 actual low models, observed metrics and Wearable controls", async ({
  page,
}) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  const predictions: any[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("websocket", (socket) =>
    socket.on("framereceived", ({ payload }) => {
      const message = JSON.parse(payload.toString());
      if (message.type === "trial_prediction")
        predictions.push(message.prediction);
    }),
  );
  await page.goto("/#/simulation");
  const select = (name: string) =>
    page.getByRole("combobox", { name, exact: true });
  await select("Input mode").selectOption("recorded");
  await expect(select("Session")).toHaveValue(/^kge_online/);
  for (const subject of ["WMJ", "KGE", "OYJ", "KHY"]) {
    await select("Participant").selectOption(subject);
    await expect(select("Session")).toHaveValue(
      new RegExp(`^${subject.toLowerCase()}_online`),
    );
    await expect(select("Session").locator("option")).toHaveCount(3);
    await select("Channel configuration").selectOption("low");
    for (const enabled of [false, true]) {
      const tta = page.getByRole("switch", { name: "TTA", exact: true });
      if ((await tta.getAttribute("aria-checked")) !== String(enabled))
        await tta.click();
      await page
        .getByRole("button", { name: "실제 EEG 재생", exact: true })
        .click();
      await expect(page.getByTestId("decision-score")).toHaveText(
        /^0\.\d{4}$|^1\.0000$/,
      );
      await page.getByRole("button", { name: "일시정지", exact: true }).click();
      const p = predictions.at(-1);
      expect(p.participant_id).toBe(subject);
      expect(p.tta_enabled).toBe(enabled);
      expect(p.channel_mode).toBe("low");
      await expect(page.getByTestId("decision-score")).toHaveText(
        p.decision_score.toFixed(4),
      );
      await expect(page.getByTestId("inference-latency")).toHaveText(
        `${p.latency_ms.toFixed(2)} ms`,
      );
      await expect(page.getByTestId("quality-gate")).toHaveText(
        p.quality.status,
      );
      await expect(page.getByTestId("observed-accuracy")).toHaveText(
        `${p.predicted_direction === p.true_direction ? "100.0" : "0.0"}% · n=1`,
      );
      await expect(page.getByTestId("observed-ba")).toHaveText("—");
    }
  }
  // Metrics must describe only received trials, rather than a full-session lookup.
  predictions.length = 0;
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await page.getByRole("slider", { name: "Playback speed" }).fill("2");
  await page
    .getByRole("button", { name: "실제 EEG 재생", exact: true })
    .click();
  await expect
    .poll(() => new Set(predictions.map((p) => p.true_direction)).size, {
      timeout: 20000,
    })
    .toBe(2);
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  const accuracy =
    predictions.filter((p) => p.predicted_direction === p.true_direction)
      .length / predictions.length;
  const ba =
    ["LEFT", "RIGHT"]
      .map((label) => {
        const trials = predictions.filter((p) => p.true_direction === label);
        return (
          trials.filter((p) => p.predicted_direction === label).length /
          trials.length
        );
      })
      .reduce((a, b) => a + b) / 2;
  await expect(page.getByTestId("observed-accuracy")).toHaveText(
    `${(100 * accuracy).toFixed(1)}% · n=${predictions.length}`,
  );
  await expect(page.getByTestId("observed-ba")).toHaveText(
    `${(100 * ba).toFixed(1)}%`,
  );
  for (const width of [390, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.screenshot({
    path: "../backend/local_cache/phase4/smart-home-1440.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: /Wearable BCI Experience/ }).click();
  await select("Participant").selectOption("KGE");
  await expect(select("Session")).toHaveValue(/^kge_online/);
  await select("Channel configuration").selectOption("low");
  await page
    .getByRole("button", { name: "실제 EEG 재생", exact: true })
    .click();
  await expect(page.getByTestId("decision-score")).not.toHaveText("—");
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  await expect(
    page.getByText(
      `${predictions.at(-1).active_channels.length} ACTIVE ELECTRODES`,
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.getByRole("img", { name: "실제 EEG 파형" })).toBeVisible();
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(page.getByTestId("observed-accuracy")).toHaveText("— · n=0");
  for (const width of [390, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.screenshot({
    path: "../backend/local_cache/phase4/wearable-1440.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
