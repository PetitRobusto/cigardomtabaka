import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const projectRoot = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  root: projectRoot,
  publicDir: false,
  plugins: [react()],
  build: {
    ssr: "scripts/storefront-prerender.mjs",
    outDir: "../static/frontend/storefront-render",
    emptyOutDir: true,
    rollupOptions: {
      external: [],
      output: { format: "es", entryFileNames: "render.mjs" },
    },
  },
  ssr: { noExternal: true },
});
