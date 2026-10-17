import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";

// Records the scripted demo as a backup video: the real UI against the real backend replaying the
// todo-app scenario (offline, no API key). Run with `npm run demo:video`.
const here = path.dirname(fileURLToPath(import.meta.url));
const python =
  process.platform === "win32"
    ? path.resolve(here, "../.venv/Scripts/python.exe")
    : path.resolve(here, "../.venv/bin/python");
const demo = path.resolve(here, "../scripts/demo.py");
const viewport = { width: 1440, height: 900 };

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: "http://localhost:5173",
    viewport,
    video: { mode: "on", size: viewport },
    launchOptions: { slowMo: 300 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport } }],
  webServer: [
    {
      command: `"${python}" "${demo}" serve --scenario todo-app --fresh --port 8000`,
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npm run dev",
      url: "http://localhost:5173",
      env: { API_URL: "http://127.0.0.1:8000" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
