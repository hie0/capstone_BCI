import { test, expect } from "@playwright/test";

test("stability pipeline stays readable across desktop, tablet and mobile", async ({
  page,
}) => {
  await page.goto("/");
  const section = page.locator(".stability-method");
  await section.scrollIntoViewIfNeeded();
  await expect(
    section.getByText("OAS Shrinkage", { exact: true }).last(),
  ).toBeVisible();
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(() => document.fonts.ready);
    await expect(section.locator("math")).toHaveCount(4);
    expect(
      await section.locator("math").evaluateAll((nodes) =>
        nodes.every((node) => {
          const r = node.getBoundingClientRect();
          const card = node.closest("article")!.getBoundingClientRect();
          return (
            node.namespaceURI === "http://www.w3.org/1998/Math/MathML" &&
            r.height > 10 &&
            r.width > 20 &&
            r.left >= card.left &&
            r.right <= card.right
          );
        }),
      ),
    ).toBe(true);
    const layout = await section.evaluate((el) => {
      const bounds = el.getBoundingClientRect();
      const cards = [...el.querySelectorAll(".stability-flow article")].map(
        (c) => {
          const r = c.getBoundingClientRect();
          return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
        },
      );
      return {
        fits: bounds.left >= 0 && bounds.right <= innerWidth,
        contentFits: [
          ...el.querySelectorAll(
            ".stability-flow article,.stability-visual-step",
          ),
        ].every((c) => c.scrollWidth <= c.clientWidth + 1),
        cards,
      };
    });
    expect(layout.fits, `${width}px section overflow`).toBe(true);
    expect(layout.contentFits, `${width}px clipped content`).toBe(true);
    for (let i = 1; i < layout.cards.length; i++) {
      const prev = layout.cards[i - 1],
        next = layout.cards[i];
      expect(next.left >= prev.right - 1 || next.top >= prev.bottom - 1).toBe(
        true,
      );
    }
    await section.screenshot({
      path: `../backend/local_cache/stability-preview/stability-${width}.png`,
    });
  }
});
