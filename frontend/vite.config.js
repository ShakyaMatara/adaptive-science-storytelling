import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite dev server runs on :5173 (the origin the Django backend allows via CORS).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
})
