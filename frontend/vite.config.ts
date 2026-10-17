/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { configDefaults } from "vitest/config";

// In development the UI calls /api/...; Vite forwards it to the FastAPI server, so no CORS setup
// is needed. Set API_URL to point at a backend on another host or port.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.API_URL ?? "http://localhost:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    css: false,
    exclude: [...configDefaults.exclude, "e2e/**"], // Playwright specs run with `npm run demo:video`
  },
});
