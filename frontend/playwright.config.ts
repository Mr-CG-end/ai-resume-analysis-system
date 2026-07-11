import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: 'python -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
      cwd: '../backend',
      url: 'http://127.0.0.1:8000/openapi.json',
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: 'pnpm dev --host 127.0.0.1 --port 5173',
      cwd: '.',
      env: {
        VITE_API_BASE_URL: 'http://127.0.0.1:8000/api/v1',
      },
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
})
