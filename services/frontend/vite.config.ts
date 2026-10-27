import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, proxy API + WebSocket to the C2 backend so the SPA is same-origin.
// Override the target with VITE_C2_TARGET when the backend is elsewhere.
const C2_TARGET = process.env.VITE_C2_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: C2_TARGET, changeOrigin: true },
      "/ws": { target: C2_TARGET, ws: true, changeOrigin: true },
    },
  },
});
