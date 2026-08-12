import { defineConfig } from "vitest/config";

// Kept separate from vite.config.ts on purpose: vitest@2 bundles vite-5 plugin
// types that clash with the project's vite@6 plugins (react/tailwind), so a plugin-
// less test config avoids the type conflict. The current tests are pure-logic (.ts,
// no JSX), so they don't need the react plugin; add it here if/when component tests
// arrive (and pin vitest to a vite-6-compatible line).
export default defineConfig({
  test: {
    environment: "jsdom",
  },
});
