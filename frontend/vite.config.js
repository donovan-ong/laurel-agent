import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // For `npm run dev`: proxy API calls to `python -m webapp`'s FastAPI backend (default port 8100),
    // so the dev server only ever serves the React app itself.
    proxy: {
      '/api': 'http://127.0.0.1:8100',
    },
  },
})
