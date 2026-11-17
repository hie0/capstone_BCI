import { test, expect } from "@playwright/test";

for (const mode of ["synthetic", "recorded"] as const) {
  test(`EEG monitor sections stay separate during ${mode} playback`, async ({
    page,
  }) => {
    await page.goto("/#/simulation?app=home");
    await page
      .getByRole("combobox", { name: "Input mode", exact: true })
      .selectOption(mode);
    if (mode === "recorded") {
      await expect(
        page.getByRole("combobox", { name: "Session", exact: true }),
      ).toHaveValue(/^kge_online/);
    }
    // The synthetic stream is deterministic here so the longer RIGHT label is exercised.
    if (mode === "synthetic")
      await page.evaluate(() => {
        Math.random = () => 0.1;
      });
    await page
      .locator(".room-panel")
      .getByRole("button", { name: /재생|시작/ })
      .click();
    await expect(page.getByTestId("command-count")).not.toHaveText("000", {
      timeout: 10000,
    });
    await expect(page.locator(".monitor > .prediction strong")).toHaveText(
      mode === "synthetic" ? "RIGHT" : /LEFT|RIGHT/,
    );

    for (const width of [390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      const layout = await page.locator(".monitor").evaluate((monitor) => {
        const box = (el: Element) => {
          const r = el.getBoundingClientRect();
          return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
        };
        const selectors = [
          ".prediction",
          ".waveform",
          ".monitor-stats",
          ".recorded-metrics",
          ".log-heading",
          ".command-history",
        ];
        return {
          sections: selectors.flatMap((selector) => {
            const el = monitor.querySelector(`:scope > ${selector}`);
            return el ? [{ selector, ...box(el) }] : [];
          }),
          overflow: document.documentElement.scrollWidth > innerWidth,
        };
      });
      expect(layout.overflow, `${mode} ${width}px horizontal overflow`).toBe(
        false,
      );
      for (let i = 0; i < layout.sections.length; i++) {
        for (const b of layout.sections.slice(i + 1)) {
          const a = layout.sections[i];
          const overlap =
            Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 &&
            Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1;
          expect(
            overlap,
            `${mode} ${width}px ${a.selector} overlaps ${b.selector}`,
          ).toBe(false);
        }
      }
      if (width >= 1024)
        await page.screenshot({
          path: `../backend/local_cache/monitor-fix/${mode}-${width}.png`,
          fullPage: true,
        });
    }
    await expect(page.getByText(/현재까지 재생한 trial 전체 기준/)).toHaveCount(
      0,
    );
    await expect(page.getByText(/세션별 Calib20 재생 결과이며/)).toHaveCount(0);
  });
}
