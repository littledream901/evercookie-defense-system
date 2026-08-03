import { resolve } from 'node:path';
import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    lib: {
      entry: resolve(__dirname, 'src/index.ts'),
      name: 'SdSdk',
      formats: ['umd', 'es'],
      fileName: (format) => (format === 'umd' ? 'sd-sdk.min.js' : 'sd-sdk.mjs'),
    },
    minify: 'esbuild',
    sourcemap: true,
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.test.ts'],
  },
});
