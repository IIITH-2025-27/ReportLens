import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on port 8000; requests to /api are passed through to it.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
