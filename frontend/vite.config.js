import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import descriptions from "./seo-descriptions.json";

// Build output → Django static/frontend/
export default defineConfig({
  plugins: [
    react(),
    {
      name: "default-seo-description",
      transformIndexHtml() {
        return [{
          tag: "meta",
          attrs: { name: "description", content: descriptions["zh-CN"] },
          injectTo: "head",
        }];
      },
    },
  ],
  base: "/static/frontend/",
  build: {
    outDir: "../static/frontend",
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: { app: 'index.html', storefront: 'src/storefront/client.tsx' },
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash].[ext]",
      },
    },
  },
  server: {
    cors: { origin: ["http://localhost:8000", "http://127.0.0.1:8000", "http://192.168.0.97:8000"] },
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/media": "http://127.0.0.1:8000",
      "/privnote": "http://127.0.0.1:8000",
      "/p": "http://127.0.0.1:8000",
    },
  },
});
