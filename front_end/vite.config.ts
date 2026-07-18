import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    watch: { usePolling: true },
    // Clickjacking hardening: the OAuth consent view (/connect/authorize)
    // mints tokens on a click — the SPA must never render inside a frame.
    // Production deployments must set the equivalent header at their edge
    // (Caddy/nginx): X-Frame-Options DENY / CSP frame-ancestors 'none'.
    headers: { 'X-Frame-Options': 'DENY' },
  },
  preview: {
    headers: { 'X-Frame-Options': 'DENY' },
  },
})
