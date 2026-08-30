import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // Keep component tests honest: a test that leaves a pending request or a
    // stray timer should fail loudly rather than leak into the next file.
    // Integration tests drive long forms through a real router and MSW; the
    // default 5s is tight for the largest of them under parallel load.
    testTimeout: 20000,
    restoreMocks: true,
    clearMocks: true,
    coverage: {
      provider: "v8",
      reportsDirectory: "coverage",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/test/**",
        "src/api/schema.d.ts",
        // Type-only modules: they compile to nothing, so there is no code to cover.
        "src/api/types.ts",
        "src/main.tsx",
        "src/vite-env.d.ts",
        "**/*.test.{ts,tsx}",
      ],
      // Every statement and line is covered; the suite fails if that slips.
      // Branches and functions stop just short: the remainder is defensive code
      // the UI cannot reach (`x instanceof Error` where only Errors arrive,
      // `?? []` on fields the schema marks non-null, a bearer-token guard behind
      // the auth route). Raise these as that code is reached or removed.
      thresholds: {
        statements: 100,
        lines: 100,
        branches: 97,
        functions: 98,
      },
    },
  },
});
