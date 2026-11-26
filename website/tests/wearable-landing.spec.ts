import { test, expect } from "@playwright/test";

test("Wearable BCI is the default and preserves smart home/recorded playback", async ({
  page,
}) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/#/simulation");
  await expect(
    page.getByRole("tab", { name: "Wearable BCI", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("tab", { name: "EEG Replay", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: /더 적은 전극으로,/ }),
  ).toBeVisible();
  const photos = page.locator(".wearable-comparison-grid img");
  await expect(photos).toHaveCount(2);
  expect(
    await photos.evaluateAll((images) =>
      images.every(
        (el) =>
          (el as HTMLImageElement).complete &&
          (el as HTMLImageElement).naturalWidth > 0,
      ),
    ),
  ).toBe(true);
  const selectMode = (mode: string) =>
    page
      .getByRole("group", { name: "웨어러블 시각화 채널 구성" })
      .getByRole("button", { name: new RegExp(`^${mode}`) });
  for (const [mode, count] of [
    ["16ch", 16],
    ["7ch", 7],
    ["5ch", 5],
  ] as const) {
    await selectMode(mode).click();
    await expect(
      page.getByText(`${count} ACTIVE ELECTRODES`, { exact: true }),
    ).toBeVisible();
    await expect(page.locator(".wearable-electrode-list .enabled")).toHaveCount(
      count,
    );
  }
  await expect(page.locator(".wearable-overview-scene canvas")).toBeVisible();
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      `${width}px overflow`,
    ).toBe(true);
    const sizes = await page
      .locator(".wearable-photo")
      .evaluateAll((els) =>
        els.map((el) => ({ width: el.clientWidth, height: el.clientHeight })),
      );
    expect(Math.abs(sizes[0].width - sizes[1].width)).toBeLessThanOrEqual(1);
    expect(Math.abs(sizes[0].height - sizes[1].height)).toBeLessThanOrEqual(1);
    await page.screenshot({
      path: `../backend/local_cache/wearable-preview/wearable-${width}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1440, height: 1100 });
  await selectMode("16ch").click();
  await page
    .getByRole("button", { name: "Smart Home 체험하기", exact: true })
    .click();
  await expect(
    page.getByRole("tab", { name: "BCI Applications", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  // Visual channel exploration must not select an inference model.
  await expect(
    page.getByRole("combobox", { name: "Channel configuration", exact: true }),
  ).toHaveValue("low");
  await page
    .getByRole("button", { name: "Lighting 메뉴", exact: true })
    .click();
  await page.getByRole("button", { name: /LEFT.*조명 끄기/ }).click();
  await expect(
    page.getByRole("button", { name: "Lighting 메뉴", exact: true }),
  ).toContainText("OFF");
  await page.getByRole("button", { name: /미니 게임/ }).click();
  await expect(
    page.getByText("미니 게임 준비 중", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: /통합 BCI 홈 제어/ }).click();
  await page
    .getByRole("combobox", { name: "Input mode", exact: true })
    .selectOption("recorded");
  await expect(
    page.getByRole("combobox", { name: "Session", exact: true }),
  ).toHaveValue(/^kge_online/);
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await page
    .getByRole("button", { name: "실제 EEG 재생", exact: true })
    .click();
  await expect(page.getByTestId("decision-score")).not.toHaveText("—");
  await expect(
    page.getByRole("img", { name: "실제 EEG 파형", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  await page.getByRole("tab", { name: "Wearable BCI", exact: true }).click();
  await selectMode("7ch").click();
  await page
    .getByRole("button", { name: "Smart Home 체험하기", exact: true })
    .click();
  await expect(
    page.getByRole("combobox", { name: "Input mode", exact: true }),
  ).toHaveValue("recorded");
  await expect(
    page.getByRole("combobox", { name: "Channel configuration", exact: true }),
  ).toHaveValue("low");
  await page
    .getByRole("button", { name: "실제 EEG 재생", exact: true })
    .click();
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  expect(errors).toEqual([]);
});
