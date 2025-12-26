import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Force Vite to use the root lucide-react package to avoid missing icon files
      'lucide-react': path.resolve(__dirname, 'node_modules/lucide-react'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5176,
    strictPort: true,
    proxy: {
      '/api': 'http://localhost:8787',
    },
    watch: {
      // Avoid spurious restarts when editors/sync tools touch env/config/cache folders.
      ignored: ['**/.env*', '**/vite.config.js', '**/.venv/**', '**/node_modules/.vite/**'],
    },
  },
});
