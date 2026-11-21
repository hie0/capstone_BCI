import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "recorded-static.spec.ts",
  timeout: 90000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4178",
    viewport: { width: 1440, height: 1100 },
    channel: "chrome",
    headless: true,
  },
  webServer: {
    command: "npm run preview -- --port 4178",
    url: "http://127.0.0.1:4178",
    reuseExistingServer: false,
  },
  reporter: "list",
});
