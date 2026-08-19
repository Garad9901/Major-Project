// Copyright (c) 2026 Yash Garad. All rights reserved.

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // Test runner config lives here rather than in a separate vitest.config.js so
  // the tests resolve modules exactly the way the application build does. A
  // second config file is a second place for aliases and JSX settings to drift.
  test: {
    // "node", not "jsdom". Every existing test renders with
    // react-dom/server's renderToStaticMarkup and asserts on the HTML string,
    // and __testutils__/renderHook.jsx installs its own requestAnimationFrame.
    // Nothing touches a live DOM, so a DOM implementation would be ~40 MB of
    // dependency bought for nothing. Component tests that need one can set
    // `// @vitest-environment jsdom` per file.
    environment: "node",
    // Only the wrappers in __tests__/ are collected. The legacy __*_test__.jsx
    // files are imported BY those wrappers; if they were collected directly
    // they would run twice and register nothing, because they contain no
    // test() calls of their own.
    include: ["src/__tests__/**/*.test.{js,jsx}"],
    // Explicit rather than inherited: the production build must never see
    // these, and .dockerignore already excludes them from the image.
    exclude: ["node_modules/**", "dist/**"],
    globals: false,
  },
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
