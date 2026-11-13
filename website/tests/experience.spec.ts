import { test, expect } from "@playwright/test";
test("all smart home commands, immediate selection, logs, reset and synthetic playback", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/#/simulation");
  await page.getByRole("button", { name: "Lighting 메뉴" }).click();
  await expect(page.getByText("DEVICE CONTROL", { exact: true })).toBeVisible({
    timeout: 500,
  });
  await page.getByRole("button", { name: /LEFT.*조명 끄기/ }).click();
  await expect(
    page.getByRole("button", { name: "Lighting 메뉴" }),
  ).toContainText("OFF");
  await page.getByRole("button", { name: /RIGHT.*조명 켜기/ }).click();
  await expect(
    page.getByRole("button", { name: "Lighting 메뉴" }),
  ).toContainText("ON");
  await page.getByRole("button", { name: "Curtains 메뉴" }).click();
  await page.getByRole("button", { name: /LEFT.*커튼 닫기/ }).click();
  await expect(
    page.getByRole("button", { name: "Curtains 메뉴" }),
  ).toContainText("CLOSED");
  await page.getByRole("button", { name: /RIGHT.*커튼 열기/ }).click();
  await expect(
    page.getByRole("button", { name: "Curtains 메뉴" }),
  ).toContainText("OPEN");
  await page.getByRole("button", { name: "Temperature 메뉴" }).click();
  await page.getByRole("button", { name: /RIGHT.*온도/ }).click();
  await expect(
    page.getByRole("button", { name: "Temperature 메뉴" }),
  ).toContainText("23°C");
  await page.getByRole("button", { name: /LEFT.*온도/ }).click();
  await expect(
    page.getByRole("button", { name: "Temperature 메뉴" }),
  ).toContainText("22°C");
  await expect(page.locator(".scene-wall-temperature")).toContainText("22°C");
  await page.getByRole("button", { name: "Television 메뉴" }).click();
  await page.getByRole("button", { name: /RIGHT.*TV 켜기/ }).click();
  await expect(
    page.getByRole("button", { name: "Television 메뉴" }),
  ).toContainText("ON");
  await page.getByRole("button", { name: /LEFT.*TV 끄기/ }).click();
  await expect(
    page.getByRole("button", { name: "Television 메뉴" }),
  ).toContainText("OFF");
  await page.getByRole("button", { name: /RIGHT.*TV 켜기/ }).click();
  await expect(page.getByTestId("command-count")).toHaveText("009");
  await page.screenshot({
    path: "tests/artifacts/smart-home-1440.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(page.getByTestId("command-count")).toHaveText("000");
  await expect(
    page.getByRole("button", { name: "Television 메뉴" }),
  ).toContainText("OFF");
  await page.getByLabel("Input mode").selectOption("synthetic");
  await page.getByRole("button", { name: "자동 데모 시작" }).click();
  await expect(page.getByTestId("command-count")).not.toHaveText("000", {
    timeout: 6000,
  });
  await page.getByRole("button", { name: "일시정지" }).click();
  const count = await page.getByTestId("command-count").textContent();
  await page.waitForTimeout(3200);
  await expect(page.getByTestId("command-count")).toHaveText(count!);
  expect(errors).toEqual([]);
});
test("wearable configuration shares state with smart home", async ({
  page,
}) => {
  await page.goto("/#/simulation");
  await page.getByRole("button", { name: /Wearable BCI Experience/ }).click();
  await page.getByRole("button", { name: /Full montage/ }).click();
  await expect(page.getByText("16 ACTIVE ELECTRODES")).toBeVisible();
  await page.getByRole("button", { name: "2D 배치도" }).click();
  await page.getByRole("button", { name: "전극 Fp1", exact: true }).click();
  await expect(page.locator(".electrode-name")).toHaveText("Fp1");
  await page.getByRole("button", { name: "RIGHT MI" }).click();
  await expect(page.getByText(/오른손 → 좌측/)).toBeVisible();
  await page.screenshot({
    path: "tests/artifacts/wearable-1440.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: /이 구성으로 스마트홈 체험/ }).click();
  await expect(page.getByLabel("Channel configuration")).toHaveValue("16ch");
  await expect(page.getByRole("tab", { name: "Model Comparison" })).toHaveCount(
    0,
  );
});
test("home research replay and mobile layout", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /더 적은 전극으로/ }),
  ).toBeVisible();
  await page.screenshot({
    path: "tests/artifacts/home-1440.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "연구 과정", exact: true }).click();
  await expect(page).toHaveURL(/#\/research#research-process$/);
  await expect(
    page.getByRole("heading", { name: "신호 처리 파이프라인" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "실험 결과", exact: true }).click();
  await expect(page).toHaveURL(/#\/research#research-results$/);
  await expect(
    page.getByRole("heading", { name: "영점조절 적용 전후 온라인 성능" }),
  ).toBeVisible();
  await expect(
    page.getByText("54.50% → 74.71%", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "연구 내용", exact: true }).click();
  await page.screenshot({
    path: "tests/artifacts/research-1440.png",
    fullPage: true,
  });
  await page
    .locator(".subject-comparison-panel .recharts-bar-rectangle")
    .first()
    .hover();
  await expect(
    page.locator(".subject-comparison-panel .recharts-tooltip-wrapper"),
  ).toContainText("16채널 기준");
  await page.getByRole("button", { name: "제외 채널" }).click();
  await page
    .getByRole("button", { name: "전극 Fp2", exact: true })
    .press("Enter");
  await expect(page.locator(".electrode-name")).toHaveText("Fp2");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "tests/artifacts/research-mobile-390.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.getByRole("link", { name: /인터랙티브 시뮬레이션/ }).click();
  await page.getByRole("tab", { name: "EEG Replay" }).click();
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect(page.getByText(/합성 trial 2 \/ 30/)).toBeVisible();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await page.getByRole("button", { name: "Reset replay" }).click();
  await expect(page.getByText(/합성 trial 1 \/ 30/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("tab", { name: /BCI Applications/ }).click();
  await expect(
    page.getByRole("button", { name: /LEFT.*이전 메뉴/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "tests/artifacts/mobile-390.png",
    fullPage: true,
  });
});
test("WebGL unavailable provides usable fallback", async ({ page }) => {
  await page.addInitScript(() => {
    const get = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...args: unknown[]
    ) {
      if (type === "webgl2" || type === "webgl") return null;
      return get.apply(this, [type, ...args] as never);
    } as typeof get;
  });
  await page.goto("/#/simulation");
  await expect(page.getByText("2D 대체 뷰 · WebGL 사용 불가")).toBeVisible();
  await page.getByRole("button", { name: "Lighting 메뉴" }).click();
  await page.getByRole("button", { name: /LEFT.*조명 끄기/ }).click();
  await expect(page.locator(".lamp")).toHaveText("◉ OFF");
});

test("fast synthetic mode confirms selection and tablet remains usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.goto("/#/simulation");
  await page.getByLabel("Input mode").selectOption("synthetic");
  await page.getByRole("slider", { name: "Playback speed" }).fill("2");
  await page.getByRole("button", { name: "자동 데모 시작" }).click();
  await expect(page.getByText("DEVICE CONTROL", { exact: true })).toBeVisible({
    timeout: 9000,
  });
  await page.getByRole("button", { name: "일시정지" }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "tests/artifacts/tablet-1024.png",
    fullPage: true,
  });
});

test("wearable core and extended concepts, 3D selection and shared model", async ({
  page,
}) => {
  await page.goto("/#/simulation?app=wearable");
  await expect(page.getByText("5 ACTIVE ELECTRODES")).toBeVisible();
  await page.getByRole("button", { name: /Extended concept/ }).click();
  await expect(page.getByText("7 ACTIVE ELECTRODES")).toBeVisible();
  await page.getByRole("button", { name: /Core channels/ }).click();
  await expect(page.getByText("5 ACTIVE ELECTRODES")).toBeVisible();
  await page.getByRole("button", { name: "C3", exact: true }).click();
  await expect(page.locator(".electrode-name")).toHaveText("C3");
  await page.getByRole("button", { name: "RIGHT MI" }).click();
  await page
    .getByRole("combobox", { name: "Model", exact: true })
    .selectOption("baseline");
  await page.getByRole("switch", { name: "Wearable TTA" }).click();
  await page.screenshot({
    path: "tests/artifacts/wearable-3d-1440.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: /이 구성으로 스마트홈 체험/ }).click();
  await expect(
    page.getByRole("combobox", { name: "Model", exact: true }),
  ).toHaveValue("baseline");
  await expect(
    page.getByRole("switch", { name: "TTA", exact: true }),
  ).toHaveAttribute("aria-checked", "false");
});
