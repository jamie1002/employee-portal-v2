import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Tailwind v4 是 CSS-first：token 一律寫在 src/index.css 的 @theme，
// 這裡不建立 tailwind.config.js（v4 會靜默忽略它，見 docs/PITFALLS.md D4）。
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.js"],
  },
});
