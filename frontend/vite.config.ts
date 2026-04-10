import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';
import solidPlugin from 'vite-plugin-solid';
import devtools from 'solid-devtools/vite';

export default defineConfig({
  plugins: [devtools(), solidPlugin(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      // For local API: '/api': 'http://localhost:5000',
      '/api': 'https://urikalender.ch',
    },
  },
  build: {
    target: 'esnext',
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],
    globals: true,
  },
});
