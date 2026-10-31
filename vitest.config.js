import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['tests/js/**/*.test.js'],
    coverage: {
      reportOnFailure: true,
      provider: 'v8',
      include: ['Game_Logic/static/js/**/*.js'],
      reporter: ['text', 'html', 'json-summary'],
      reportsDirectory: 'coverage/js',
      thresholds: { 100: true },
    },
  },
});
