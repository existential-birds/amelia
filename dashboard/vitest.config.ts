import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config';

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: 'jsdom',
      environmentOptions: {
        jsdom: {
          url: 'http://localhost:8420',
        },
      },
      setupFiles: './src/test/setup.ts',
    },
  })
);
