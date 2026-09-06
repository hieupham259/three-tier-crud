import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// `server.proxy` only affects `vite dev` on a workstation; nothing here reaches the bundle.
// In Kubernetes the same /api prefix is proxied by nginx.conf to the backend Service.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  build: {
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
})
