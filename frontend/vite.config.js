import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Build output → Django static/price-tracker/
export default defineConfig({
  plugins: [react()],
  base: '/static/price-tracker/',
  build: {
    outDir: '../static/price-tracker',
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
