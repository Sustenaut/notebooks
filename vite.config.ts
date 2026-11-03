import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";

// The widget, built for anywidget into notebooks_lib/static/: one ES module with React, @sustenaut/ui and its
// styles inside. The unit tests run in jsdom; their LCOV report goes to the CI's sonar job.
export default defineConfig(({ command }) => ({
  plugins: [tailwindcss()],
  // @sustenaut/ui ships its TypeScript: compile its JSX as this project's.
  esbuild: { jsx: "automatic" },
  // React's production build in the bundle; the tests keep its development build, which has act().
  define: command === "build" ? { "process.env.NODE_ENV": JSON.stringify("production") } : {},
  build: {
    outDir: "notebooks_lib/static",
    emptyOutDir: true,
    minify: true,
    lib: { entry: "widget/schema_form.tsx", formats: ["es"], fileName: () => "schema_form.js" },
  },
  test: {
    environment: "jsdom",
    css: true,
    server: { deps: { inline: ["@sustenaut/ui"] } },
    include: ["widget/**/*.test.tsx"],
    coverage: {
      provider: "v8",
      include: ["widget/**/*.tsx"],
      exclude: ["widget/**/*.test.tsx"],
      reporter: ["text-summary", "lcov"],
      reportsDirectory: "coverage",
    },
  },
}));
