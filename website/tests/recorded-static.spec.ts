import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { BackendPrediction } from "../src/data/backend";
const root = new URL("../public/recorded-eeg/", import.meta.url);
const manifest = JSON.parse(
  readFileSync(new URL("manifest.json", root), "utf8"),
);
type Session = {
  participant_id: string;
  session_id: string;
  replays: Record<string, { file: string }>;
};
const sessions = manifest.sessions as Session[];
const asset = (s: Session, key: string): { predictions: BackendPrediction[] } =>
  JSON.parse(readFileSync(new URL(s.replays[key].file, root), "utf8"));
async function recorded(page: Page) {
  await page.goto("/#/simulation?app=home");
  await page
    .getByRole("combobox", { name: "Input mode", exact: true })
    .selectOption("recorded");
  await expect(
    page.getByRole("combobox", { name: "Session", exact: true }),
  ).toHaveValue(/^kge_online/);
}
for (const subject of ["KGE", "KHY", "OYJ", "WMJ"]) {
  test(`${subject}: all sessions and 16ch/low × TTA off/on replay actual exported predictions without Backend`, async ({
    page,
  }) => {
    const forbidden: string[] = [];
    page.on("request", (r) => {
      if (/\/(api|ws)\//.test(r.url())) forbidden.push(r.url());
    });
    page.on("websocket", (ws) => forbidden.push(ws.url()));
    await recorded(page);
    await page
      .getByRole("combobox", { name: "Participant", exact: true })
      .selectOption(subject);
    await expect(
      page.getByRole("combobox", { name: "Session", exact: true }),
    ).toHaveValue(new RegExp(`^${subject.toLowerCase()}_online`));
    for (const session of sessions.filter(
      (s) => s.participant_id === subject,
    )) {
      await page
        .getByRole("combobox", { name: "Session", exact: true })
        .selectOption(session.session_id);
      for (const channel of ["16ch", "low"])
        for (const tta of [false, true]) {
          const toggle = page.getByRole("switch", { name: "TTA", exact: true });
          if (((await toggle.getAttribute("aria-checked")) === "true") !== tta)
            await toggle.click();
          await page
            .getByRole("combobox", {
              name: "Channel configuration",
              exact: true,
            })
            .selectOption(channel);
          const expected = asset(
            session,
            `${channel}__tta_${tta ? "on" : "off"}`,
          ).predictions[0];
          await page
            .getByRole("button", { name: "실제 EEG 재생", exact: true })
            .click();
          await expect(page.getByTestId("decision-score")).toHaveText(
            expected.decision_score.toFixed(4),
          );
          await page
            .getByRole("button", { name: "일시정지", exact: true })
            .evaluate((button) => (button as HTMLButtonElement).click());
          await expect(page.locator(".prediction strong")).toHaveText(
            expected.predicted_direction,
          );
          await expect(page.getByTestId("quality-gate")).toHaveText(
            expected.quality.status,
          );
          await expect(page.getByTestId("observed-accuracy")).toContainText(
            "n=1",
          );
          await expect(
            page.getByRole("img", { name: "실제 EEG 파형" }),
          ).toBeVisible();
          await expect(
            page.getByRole("img", { name: "실제 EEG 파형" }),
          ).toHaveAttribute(
            "data-channels",
            expected.active_channels.join(","),
          );
          await expect(
            page.getByRole("img", { name: "실제 EEG 파형" }).locator("canvas"),
          ).toHaveCount(1);
        }
    }
    expect(forbidden).toEqual([]);
  });
}

test("pause/resume/reset/speed and responsive layouts preserve the chronological replay", async ({
  page,
}) => {
  await recorded(page);
  const s = sessions.find((s) => s.participant_id === "KGE")!;
  await page
    .getByRole("combobox", { name: "Session", exact: true })
    .selectOption(s.session_id);
  const expected = asset(s, "low__tta_on").predictions;
  await page
    .getByRole("button", { name: "Lighting 메뉴", exact: true })
    .click();
  await page.getByRole("slider", { name: "Playback speed" }).fill("2");
  await page
    .getByRole("button", { name: "실제 EEG 재생", exact: true })
    .click();
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=2");
  await page
    .getByRole("button", { name: "일시정지", exact: true })
    .evaluate((button) => (button as HTMLButtonElement).click());
  await expect(page.getByTestId("decision-score")).toHaveText(
    expected[1].decision_score.toFixed(4),
  );
  const count = await page.getByTestId("command-count").textContent();
  const metric = await page.getByTestId("observed-accuracy").textContent();
  await page.waitForTimeout(1300);
  await expect(page.getByTestId("observed-accuracy")).toHaveText(metric!);
  await expect(page.getByTestId("command-count")).toHaveText(count!);
  expect(Number(count)).toBe(
    expected.slice(0, 2).filter((p) => p.quality.is_clean).length,
  );
  await page
    .getByRole("button", { name: "실제 EEG 재생", exact: true })
    .click();
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=3");
  await page
    .getByRole("button", { name: "일시정지", exact: true })
    .evaluate((button) => (button as HTMLButtonElement).click());
  await expect(page.getByTestId("decision-score")).toHaveText(
    expected[2].decision_score.toFixed(4),
  );
  for (const width of [390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    const overflow = await page.evaluate(() => ({
      width: innerWidth,
      scroll: document.documentElement.scrollWidth,
      elements: [...document.querySelectorAll("main *")]
        .map((e) => ({
          tag: e.tagName,
          name: e.className?.toString(),
          right: e.getBoundingClientRect().right,
        }))
        .filter((e) => e.right > innerWidth + 1)
        .slice(0, 12),
    }));
    if (overflow.scroll > overflow.width)
      await page.screenshot({
        path: `../backend/local_cache/recorded-static-overflow-${width}.png`,
        fullPage: true,
      });
    expect(overflow.scroll, JSON.stringify(overflow)).toBeLessThanOrEqual(
      overflow.width,
    );
  }
  await page.screenshot({
    path: "../backend/local_cache/recorded-static-1440.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(page.getByTestId("command-count")).toHaveText("000");
  await expect(page.getByTestId("observed-accuracy")).toContainText("n=0");
  await page
    .getByRole("button", { name: "실제 EEG 재생", exact: true })
    .click();
  await expect(page.getByTestId("decision-score")).toHaveText(
    expected[0].decision_score.toFixed(4),
  );
});

test("missing replay data remains explicit; no synthetic or live Backend fallback", async ({
  page,
}) => {
  await page.route("**/recorded-eeg/manifest.json", (route) => route.abort());
  await page.goto("/#/simulation?app=home");
  await page
    .getByRole("combobox", { name: "Input mode", exact: true })
    .selectOption("recorded");
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByTestId("command-count")).toHaveText("000");
  await expect(
    page.getByText("Synthetic EEG Demo", { exact: true }),
  ).toHaveCount(0);
});

test("corrupt prediction asset fails integrity validation before any command", async ({
  page,
}) => {
  await page.route("**/recorded-eeg/*-tta-*.json", (route) => route.continue());
  await page.route(
    /\/recorded-eeg\/(?!manifest\.json)[^/]+\.json/,
    async (route) => {
      const response = await route.fetch();
      await route.fulfill({ response, body: (await response.text()) + " " });
    },
  );
  await recorded(page);
  await page
    .getByRole("button", { name: "실제 EEG 재생", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(/크기|무결성/);
  await expect(page.getByTestId("command-count")).toHaveText("000");
  await expect(page.getByTestId("decision-score")).toHaveText("—");
});

test("Neuro Runner consumes the same recorded model prediction without server inference", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (r) => {
    if (/\/(api|ws)\//.test(r.url())) requests.push(r.url());
  });
  page.on("websocket", (ws) => requests.push(ws.url()));
  await page.goto("/#/simulation?app=game");
  await page
    .getByRole("combobox", { name: "Input mode", exact: true })
    .selectOption("recorded");
  await expect(
    page.getByRole("combobox", { name: "Session", exact: true }),
  ).toHaveValue(/^kge_online/);
  const s = sessions.find((s) => s.participant_id === "KGE")!;
  const expected = asset(s, "low__tta_on").predictions[0];
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.getByTestId("decision-score")).toHaveText(
    expected.decision_score.toFixed(4),
  );
  await expect(page.locator(".runner-monitor .command-history")).toContainText(
    "Trial 1",
    { timeout: 12000 },
  );
  await page
    .getByRole("button", { name: "Pause", exact: true })
    .evaluate((button) => (button as HTMLButtonElement).click());
  await expect(page.getByRole("img", { name: "실제 EEG 파형" })).toBeVisible();
  expect(requests).toEqual([]);
});
