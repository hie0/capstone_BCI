import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "./",
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000" },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/three/")) return "three";
          if (id.includes("node_modules/recharts/")) return "charts";
        },
      },
    },
  },
});
