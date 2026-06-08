import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 8421,
    proxy: {
      '/api': {
        target: 'http://localhost:8420',
        changeOrigin: true,
      },
      '/ws': {
        target: 'http://localhost:8420',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../amelia/server/static',
    emptyOutDir: true,
    sourcemap: true,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'react-vendor',
              test: /node_modules\/(react|react-dom)\//,
            },
            {
              name: 'router',
              test: /node_modules\/react-router-dom\//,
            },
            {
              name: 'radix',
              test: /node_modules\/@radix-ui\/react-(collapsible|dialog|dropdown-menu|scroll-area|slot|tooltip)\//,
            },
          ],
        },
      },
    },
  },
});
