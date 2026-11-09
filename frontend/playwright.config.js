import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', timeout: 30000, workers: 1,
  use: { baseURL: 'http://127.0.0.1:5178', channel: 'chrome', headless: true },
  webServer: {
    command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5178`,
    url: 'http://127.0.0.1:5178', reuseExistingServer: false,
    env: { VITE_API_URL: 'http://127.0.0.1:5178' },
  },
});
