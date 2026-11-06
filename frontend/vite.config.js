import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [svelte()],
  root: '.',

  // Required for Tauri — assets must use relative paths in the bundle
  base: process.env.TAURI_ENV_DEV === 'true' ? '/' : './',

  // Vite dev server
  server: {
    port: 5173,
    // Allow Tauri dev window to connect
    host: process.env.TAURI_DEV_HOST || 'localhost',
    strictPort: true,
    // Proxy /api to FastAPI backend (dev only — Tauri prod uses direct URL)
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      }
    }
  },

  // Ensure build output goes to dist/ (matches tauri.conf.json frontendDist)
  build: {
    outDir: 'dist',
  },

  // Tauri uses ES modules
  envPrefix: ['VITE_', 'TAURI_'],
});
