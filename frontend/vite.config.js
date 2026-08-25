import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Build output → Django static/frontend/
export default defineConfig({
  plugins: [react()],
  base: '/static/frontend/',
  build: {
    outDir: '../static/frontend',
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
    cors: { origin: 'http://192.168.0.97:8000' },
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/media': 'http://127.0.0.1:8000',
    },
  },
})
