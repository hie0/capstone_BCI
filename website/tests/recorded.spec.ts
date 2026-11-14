import { test, expect } from "@playwright/test";

test("actual Recorded EEG controls devices, pauses, resets and preserves layouts", async ({
  page,
}) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  page.on("pageerror", (e) => {
    errors.push(e.message);
    console.log(e.stack);
  });
  await page.goto("/#/simulation");
  await page.getByRole("button", { name: "Lighting 메뉴" }).click();
  await page
    .getByRole("combobox", { name: "Input mode", exact: true })
    .selectOption("recorded");
  await expect(
    page.getByRole("combobox", { name: "Session", exact: true }),
  ).toHaveValue(/^kge_online/);
  await expect(
    page.getByRole("combobox", { name: "Model", exact: true }),
  ).toContainText("Reg-CSP");
  await page
    .getByRole("button", { name: "실제 EEG 재생", exact: true })
    .click();
  await expect(page.getByTestId("command-count")).not.toHaveText("000", {
    timeout: 12000,
  });
  await expect(page.getByRole("img", { name: "실제 EEG 파형" })).toBeVisible();
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  const count = await page.getByTestId("command-count").textContent();
  await page.waitForTimeout(2300);
  await expect(page.getByTestId("command-count")).toHaveText(count!);
  await page.screenshot({
    path: "../backend/local_cache/migration/recorded-home-1440.png",
    fullPage: true,
  });
  for (const width of [390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.screenshot({
    path: "../backend/local_cache/migration/recorded-home-1440-final.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(page.getByTestId("command-count")).toHaveText("000");
  for (const subject of ["WMJ", "KGE", "OYJ", "KHY"]) {
    await page
      .getByRole("combobox", { name: "Participant", exact: true })
      .selectOption(subject);
    await expect(
      page.getByRole("combobox", { name: "Session", exact: true }),
    ).toHaveValue(new RegExp(`^${subject.toLowerCase()}_online`));
    await page
      .getByRole("button", { name: "실제 EEG 재생", exact: true })
      .click();
    await expect(page.locator(".prediction strong")).toHaveText(/LEFT|RIGHT/, {
      timeout: 8000,
    });
    await page.getByRole("button", { name: "일시정지", exact: true }).click();
    await page.getByRole("switch", { name: "TTA", exact: true }).click();
    await page
      .getByRole("combobox", { name: "Channel configuration", exact: true })
      .selectOption("16ch");
    await page
      .getByRole("button", { name: "실제 EEG 재생", exact: true })
      .click();
    await expect(page.locator(".prediction strong")).toHaveText(/LEFT|RIGHT/, {
      timeout: 8000,
    });
    await page.getByRole("button", { name: "일시정지", exact: true }).click();
  }
  await page.getByRole("button", { name: /Wearable BCI Experience/ }).click();
  await expect(
    page.getByText("16 ACTIVE ELECTRODES", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "2D 배치도", exact: true }).click();
  await page.getByRole("button", { name: "전극 Fp1", exact: true }).click();
  await expect(page.locator(".electrode-name")).toHaveText("Fp1");
  await page.getByRole("tab", { name: "EEG Replay", exact: true }).click();
  await page.getByRole("button", { name: "Reset replay", exact: true }).click();
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect(page.getByText(/Recorded trial 1 \/ 60/)).toBeVisible({
    timeout: 8000,
  });
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(page.getByRole("img", { name: "실제 EEG 파형" })).toBeVisible();
  await page.screenshot({
    path: "../backend/local_cache/migration/recorded-replay-1440.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("backend failure stays explicit and never substitutes synthetic EEG", async ({
  page,
}) => {
  await page.route("**/api/sessions**", (route) => route.abort());
  await page.goto("/#/simulation");
  await page
    .getByRole("combobox", { name: "Input mode", exact: true })
    .selectOption("recorded");
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByTestId("command-count")).toHaveText("000");
  await expect(page.getByRole("img", { name: "실제 EEG 파형" })).toBeVisible();
  await expect(
    page.getByText("Synthetic EEG Demo", { exact: true }),
  ).toHaveCount(0);
});
