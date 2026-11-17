import { test, expect } from "@playwright/test";

// Independent source fixtures: Baseline, Low+TTA, percentage-point improvement.
const ids = ["KGE", "KHY", "OYJ", "WMJ", "ALL"];
const online = [
  [65.59, 72.62, 7.03],
  [59.44, 66.51, 7.07],
  [74.78, 81.45, 6.67],
  [70.03, 76.35, 6.32],
  [67.46, 74.23, 6.77],
];
const loso = [
  [63.95, 71.09, 7.14],
  [57.79, 64.91, 7.12],
  [64.97, 67.53, 2.56],
  [66.3, 83.33, 17.03],
];

test("research charts compare two conditions using initials and identical metric selection", async ({
  page,
}) => {
  test.setTimeout(60000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  const result = page.locator("#research-results");
  const dashboard = page.locator(
    ".research-results-detail .subject-results-dashboard",
  );
  for (const value of ["16 → 5–7", "71.72%", "74.23%", "65.77%"])
    await expect(page.locator(".metrics")).toContainText(value);
  expect(
    await dashboard.locator(".subject-tabs strong").allTextContents(),
  ).toEqual(["ALL", ...ids.slice(0, 4)]);
  await expect(
    dashboard.getByRole("button", { name: "Macro-F1", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  for (const [scope, fixture] of [
    [result, online],
    [dashboard, loso],
  ] as const) {
    const chart = scope.locator(".benchmark-chart");
    await scope.scrollIntoViewIfNeeded();
    await expect(
      chart.locator("[data-participant][data-condition]"),
    ).toHaveCount(fixture.length * 2);
    expect(
      await chart.locator(".benchmark-legend > span").allTextContents(),
    ).toEqual(["16ch Baseline", "Low Channel + TTA"]);
    const conditions = await chart
      .locator("[data-condition]")
      .evaluateAll((nodes) => [
        ...new Set(nodes.map((n) => n.getAttribute("data-condition"))),
      ]);
    expect(conditions).toEqual(["baseline", "lowTta"]);
    const ticks = (await chart.locator("svg text").allTextContents()).filter(
      (text) => /^(50|60|70|80|90|100)%$/.test(text),
    );
    expect(ticks).toEqual(["50%", "60%", "70%", "80%", "90%", "100%"]);
    await chart.locator(".benchmark-values > summary").click();
    const rows = chart.locator("tbody tr");
    for (let i = 0; i < fixture.length; i++) {
      await expect(rows.nth(i).locator("th")).toHaveText(ids[i]);
      expect(await rows.nth(i).locator("td").allTextContents()).toEqual(
        fixture[i].map((n, j) =>
          j === 2 ? `+${n.toFixed(2)}%p` : `${n.toFixed(2)}%`,
        ),
      );
    }
    await chart.locator(".benchmark-values > summary").click();
  }
  await dashboard
    .getByRole("button", { name: "OYJ Participant OYJ", exact: true })
    .click();
  for (const [metric, baseline, proposed] of [
    ["Macro-F1", "64.97%", "67.53%"],
    ["BA", "68.00%", "75.82%"],
    ["AUC", "0.7420", "0.8123"],
  ]) {
    await dashboard.getByRole("button", { name: metric, exact: true }).click();
    await expect(
      dashboard.locator("[data-participant][data-condition]"),
    ).toHaveCount(2);
    await expect(dashboard.locator('[data-participant="OYJ"]')).toHaveCount(2);
    await expect(dashboard.locator(".subject-summary")).toContainText(baseline);
    await expect(dashboard.locator(".subject-summary")).toContainText(proposed);
    await dashboard.locator('[data-condition="lowTta"] path').hover();
    await expect(dashboard.locator(".benchmark-tooltip")).toContainText("OYJ");
    await expect(dashboard.locator(".benchmark-tooltip")).toContainText(
      proposed,
    );
  }
  await dashboard
    .getByRole("button", { name: "Macro-F1", exact: true })
    .click();
  await dashboard
    .getByRole("button", { name: "WMJ Participant WMJ", exact: true })
    .click();
  await expect(dashboard.getByTestId("loso-improvement")).toHaveText(
    "+17.03%p",
  );
  await expect(dashboard.locator(".subject-summary")).toContainText("83.33%");
  await dashboard
    .getByRole("button", { name: "ALL 4인 비교", exact: true })
    .click();
  await expect(
    dashboard.locator("[data-participant][data-condition]"),
  ).toHaveCount(8);
  await expect(dashboard.getByTestId("loso-improvement")).toHaveText("+8.47%p");
  await expect(dashboard.locator(".external-model-result")).toContainText(
    "59.33% → 65.77%",
  );
  await expect(result).toContainText("1.90 × 10⁻⁸");
  await expect(result).toContainText("2.85 × 10⁻⁷");
  await expect(result).toContainText("세션 단위 평균 차이 +6.79%p");
  await result.locator(".legacy-ba-details > summary").click();
  await expect(result.locator(".legacy-ba-details")).toContainText("54.50%");
  await expect(result.locator(".legacy-ba-details")).toContainText("74.71%");
  await result.locator(".legacy-ba-details > summary").click();
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const scope of [result, dashboard]) {
      await scope.scrollIntoViewIfNeeded();
      await page.mouse.move(0, 0);
      const box = await scope.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      const chart = scope.locator(".benchmark-chart");
      expect(
        await chart
          .locator(".benchmark-chart-canvas")
          .evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
      ).toBe(true);
      const overlap = await chart
        .locator("[data-condition] path")
        .evaluateAll((nodes) => {
          const boxes = nodes.map((n) => n.getBoundingClientRect());
          return boxes.some((a, i) =>
            boxes
              .slice(i + 1)
              .some(
                (b) =>
                  Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 &&
                  Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1,
              ),
          );
        });
      expect(overlap, `${width}px bars overlap`).toBe(false);
    }
    await result.screenshot({
      path: `../backend/local_cache/two-condition-preview/online-${width}.png`,
    });
    await dashboard.screenshot({
      path: `../backend/local_cache/two-condition-preview/loso-${width}.png`,
    });
  }
  expect(errors).toEqual([]);
});
