// Copyright (c) 2026 Yash Garad. All rights reserved.

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // The Caddy proxy forwards requests with the server's hostname/IP as the
    // Host header; allow any host so Vite's dev server doesn't reject them.
    allowedHosts: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET || "http://backend:8000",
        changeOrigin: true,
      },
    },
  },
});
