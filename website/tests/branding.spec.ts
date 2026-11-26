import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
const assets = new URL("../public/brand/", import.meta.url);
const info = JSON.parse(
  readFileSync(new URL("asset-info.json", assets), "utf8"),
);

test("brand originals are preserved, icons have requested sizes and HTML points to valid assets", async ({
  page,
  request,
}) => {
  for (const [i, name] of [
    "neurolink-logo.png",
    "neurolink-symbol.png",
  ].entries()) {
    const hash = createHash("sha256")
      .update(readFileSync(new URL(name, assets)))
      .digest("hex");
    expect(hash).toBe(info.sourceHashes[i]);
  }
  const ico = readFileSync(new URL("favicon.ico", assets));
  expect(ico.readUInt16LE(2)).toBe(1);
  expect(ico.readUInt16LE(4)).toBe(3);
  expect([ico[6], ico[22], ico[38]]).toEqual([16, 32, 48]);
  await page.goto("/");
  const links = await page
    .locator('link[rel="icon"],link[rel="apple-touch-icon"]')
    .evaluateAll((nodes) =>
      nodes.map((node) => (node as HTMLLinkElement).href),
    );
  expect(links).toHaveLength(5);
  for (const url of links) expect((await request.get(url)).ok()).toBe(true);
  for (const size of [16, 32, 48, 180]) {
    const file =
      size === 180 ? "apple-touch-icon.png" : `favicon-${size}x${size}.png`;
    const dimensions = await page.evaluate(
      async (source) => {
        const img = new Image();
        img.src = source;
        await img.decode();
        return [img.width, img.height];
      },
      new URL(`brand/${file}`, page.url()).href,
    );
    expect(dimensions).toEqual([size, size]);
  }
  await page.setViewportSize({ width: 900, height: 260 });
  await page.setContent(`<body style="margin:0;padding:28px;background:#F5F7FA;color:#253F55;font:14px system-ui"><h2 style="margin:0 0 24px">NEUROLINK · Favicon &amp; App Icon</h2><div style="display:flex;align-items:center;gap:36px">${[16,32,48,180].map(size => `<figure style="margin:0;text-align:center"><img src="/brand/${size === 180 ? 'apple-touch-icon.png' : `favicon-${size}x${size}.png`}" width="${Math.min(96,size)}" height="${Math.min(96,size)}"><figcaption style="margin-top:12px">${size} × ${size}</figcaption></figure>`).join('')}</div></body>`);
  await page.locator('img').evaluateAll(images => Promise.all(images.map(img => (img as HTMLImageElement).decode())));
  await page.screenshot({ path: '../backend/local_cache/branding/favicon-preview.png' });

});

test("shared header/footer use one provided full logo and preserve responsive header dimensions", async ({
  page,
}) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/#/simulation?app=communication");
    const header = page.getByRole("banner");
    const footer = page.getByRole("contentinfo");
    for (const area of [header, footer]) {
      const image = area.getByRole("img", {
        name: "NEUROLINK · MI-BCI RESEARCH LAB",
        exact: true,
      });
      await expect(image).toHaveCount(1);
      await image.evaluate((img: HTMLImageElement) => img.decode());
      const box = await image.boundingBox();
      expect(box).not.toBeNull();
      expect(Math.abs(box!.width / box!.height - 720 / 184)).toBeLessThan(0.01);
      expect(await area.locator(".brand-symbol").count()).toBe(0);
    }
    expect((await header.boundingBox())!.height).toBe(width > 760 ? 80 : 112);
    // Check the shared branding without altering the existing Communication
    // Board's separate mobile progress-strip layout.
    for (const region of [header, footer]) {
      const box = await region.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      const logo = await region.getByRole("img", { name: "NEUROLINK · MI-BCI RESEARCH LAB", exact: true }).boundingBox();
      expect(logo!.x + logo!.width).toBeLessThanOrEqual(width);
    }
    const logoBox = await header.getByRole("img", { name: "NEUROLINK · MI-BCI RESEARCH LAB", exact: true }).boundingBox();
    const navBox = await header.getByRole("navigation").boundingBox();
    expect(logoBox!.x + logoBox!.width <= navBox!.x || logoBox!.y + logoBox!.height <= navBox!.y).toBe(true);
    await header.screenshot({
      path: `../backend/local_cache/branding/header-${width}.png`,
    });
    await footer.screenshot({
      path: `../backend/local_cache/branding/footer-${width}.png`,
    });
    await header
      .getByRole("link", { name: "NEUROLINK 홈", exact: true })
      .click();
    await expect(page).toHaveURL(/#\/$/);
    await expect(
      page.getByRole("heading", { name: /더 적은 전극으로/ }),
    ).toBeVisible();
  }
});

test("brand files also load from a GitHub Pages style subdirectory", async ({
  page,
}) => {
  // Serve the built site through a prefixed URL, preserving relative asset paths.
  await page.route("**/capstone_BCI/**", async (route) => {
    const url = new URL(route.request().url());
    url.pathname = url.pathname.replace(/^\/capstone_BCI/, "");
    const response = await route.fetch({ url: url.href });
    await route.fulfill({ response });
  });
  await page.goto("/capstone_BCI/#/simulation?app=communication");
  const image = page
    .getByRole("banner")
    .getByRole("img", { name: "NEUROLINK · MI-BCI RESEARCH LAB", exact: true });
  await image.evaluate((img: HTMLImageElement) => img.decode());
  expect(
    await image.evaluate((img: HTMLImageElement) => img.currentSrc),
  ).toContain("/capstone_BCI/brand/");
  expect(
    await page.locator('link[rel="icon"][sizes="32x32"]').getAttribute("href"),
  ).toMatch(/^\.\/brand\//);
});
