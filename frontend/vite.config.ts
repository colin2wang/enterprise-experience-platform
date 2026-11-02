import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// Build output goes to ../web so FastAPI keeps serving the SPA at /web.
export default defineConfig({
  base: "/web/",
  plugins: [vue()],
  build: {
    outDir: "../web",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/v1": {
        target: "http://127.0.0.1:8100",
        changeOrigin: true,
      },
    },
  },
});
