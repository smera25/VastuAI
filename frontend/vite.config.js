import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend URL comes from VITE_API_BASE_URL (see .env.example) - nothing machine-specific is hardcoded.
export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173 },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
  },
})
