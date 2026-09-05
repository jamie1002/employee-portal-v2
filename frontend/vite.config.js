import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Tailwind v4 是 CSS-first：token 一律寫在 src/index.css 的 @theme，
// 這裡不建立 tailwind.config.js（v4 會靜默忽略它，見 docs/PITFALLS.md D4）。
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // 綁 0.0.0.0 而非預設的 localhost，讓同一個區網下的手機／平板也能連
    // http://<這台電腦的區網 IP>:5173 測試（後端 CORS_ORIGINS 也要放行該來源）。
    host: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.js"],
  },
});
