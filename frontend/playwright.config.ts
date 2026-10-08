import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
process.loadEnvFile('../.env');
if (!process.env.TEST_DATABASE_URL?.endsWith('/erp_phase1_test') || !process.env.MOCK_TEST_DATABASE_URL?.endsWith('/erp_phase1_test')) throw new Error('Browser tests require erp_phase1_test');
const python = '"' + resolve(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python') + '"';
const env = { APP_ENV: 'test', DATABASE_URL: process.env.TEST_DATABASE_URL!, MOCK_DATABASE_URL: process.env.MOCK_TEST_DATABASE_URL!, BOSS_URL: 'http://127.0.0.1:8002', BOSS_TOKEN: process.env.BOSS_TOKEN!, AI_MODE: 'offline', DEEPSEEK_API_KEY: '' };
const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
export default defineConfig({
  testDir: './tests/e2e', fullyParallel: false, workers: 1, timeout: 60000, retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:5174', viewport: { width: 1440, height: 1000 }, trace: 'off', screenshot: 'only-on-failure', launchOptions: existsSync(edge) ? { executablePath: edge } : {} },
  webServer: [
    { command: `${python} -m uvicorn app.main:app --app-dir ../mock_boss --port 8002 --no-access-log`, url: 'http://127.0.0.1:8002/health/ready', reuseExistingServer: true, env },
    { command: `${python} -m uvicorn app.main:app --app-dir ../backend --port 8003 --no-access-log`, url: 'http://127.0.0.1:8003/health/ready', env: { ...env, WEB_ORIGIN: 'http://127.0.0.1:5174' } },
    { command: 'npm run dev -- --port 5174 --strictPort', url: 'http://127.0.0.1:5174', env: { ERP_PROXY_TARGET: 'http://127.0.0.1:8003' } },
    { command: `${python} -m uvicorn app.main:app --app-dir ../backend --port 8004 --no-access-log`, url: 'http://127.0.0.1:8004/health/ready', env: { ...env, AI_MODE: 'deepseek', DEEPSEEK_API_KEY: '', WEB_ORIGIN: 'http://127.0.0.1:5175' } },
    { command: 'npm run dev -- --port 5175 --strictPort', url: 'http://127.0.0.1:5175', env: { ERP_PROXY_TARGET: 'http://127.0.0.1:8004' } },
  ],
});
