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
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react/') || id.includes('node_modules/react-dom/')) {
            return 'react-vendor';
          }
          if (id.includes('node_modules/react-router-dom/')) {
            return 'router';
          }
          if (/node_modules\/@radix-ui\/react-(collapsible|dialog|dropdown-menu|scroll-area|slot|tooltip)\//.test(id)) {
            return 'radix';
          }
        },
      },
    },
  },
});
