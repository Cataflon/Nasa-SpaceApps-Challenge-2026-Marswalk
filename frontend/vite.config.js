import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Mock-urile din shared/contracts, importabile ca `@contracts/site.json`.
      "@contracts": fileURLToPath(new URL("../shared/contracts", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    fs: { allow: [".."] },
    proxy: {
      "/api": { target: BACKEND, ws: true },
      "/static": { target: BACKEND },
    },
  },
});
