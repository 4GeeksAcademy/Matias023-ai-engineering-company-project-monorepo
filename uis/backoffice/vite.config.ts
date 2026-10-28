import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3001,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || (process.env.CODESPACES === 'true' || process.env.CODESPACE_NAME ? 'http://127.0.0.1:8000' : 'http://backend:8000'),
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
