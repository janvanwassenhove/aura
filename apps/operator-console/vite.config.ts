import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [tailwindcss(), vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    // U350: happy-dom no longer reaches the tests' `localStorage` on its own.
    // See tests/setup.ts — it is not boilerplate, it is load-bearing.
    setupFiles: ['./tests/setup.ts'],
  },
})
