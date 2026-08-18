import { defineConfig } from "vitest/config";

// Kept separate from vite.config.ts on purpose: component (.tsx) tests already
// run fine here without the react plugin -- esbuild's default JSX transform
// handles them; the plugin is only needed for fast-refresh/dev-server features,
// not for vitest's transform step.
export default defineConfig({
  test: {
    environment: "jsdom",
    coverage: {
      provider: "v8",
      reporter: ["text", "text-summary"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/main.tsx"],
    },
  },
});
