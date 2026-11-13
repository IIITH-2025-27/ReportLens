import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// The lite API runs on port 8001; requests to /api are passed through to it.
// The stylesheet is shared with web/frontend (src/main.jsx imports it), so the dev server may read the repo root.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: { "/api": "http://localhost:8001" },
    fs: { allow: [fileURLToPath(new URL("../..", import.meta.url))] },
  },
});
