import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy API calls to the Portal backend (Docker Compose exposes it on 8081)
      // We mount the API under /api to avoid clashing with SPA routes like /tests or /runs.
      "/api": {
        target: "http://localhost:8081",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    }
  },
  build: {
    outDir: "dist",
    sourcemap: true
  }
});
