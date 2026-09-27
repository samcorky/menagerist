import { defineConfig, devices } from '@playwright/test';

const E2E_DATABASE_URL = 'postgresql+asyncpg://menagerist:menagerist@localhost:55433/menagerist';

export default defineConfig({
	testDir: './e2e',
	// A single shared dev backend/frontend/database backs every worker (no
	// per-worker isolation), so parallel workers cause real contention and
	// timeouts under load rather than exercising independent state.
	fullyParallel: false,
	workers: 1,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 1 : 0,
	reporter: 'list',
	timeout: 30_000,
	expect: { timeout: 10_000 },
	use: {
		baseURL: 'http://localhost:5173',
		trace: 'on-first-retry'
	},
	projects: [
		{
			name: 'chromium',
			use: { ...devices['Desktop Chrome'] }
		}
	],
	webServer: [
		{
			command: 'uv run menagerist serve --host 127.0.0.1 --port 8000',
			cwd: '..',
			env: { MENAGERIST_DATABASE_URL: E2E_DATABASE_URL },
			url: 'http://localhost:8000/api/health/ready',
			reuseExistingServer: !process.env.CI,
			timeout: 60_000
		},
		{
			command: 'npm run dev -- --port 5173',
			cwd: '.',
			url: 'http://localhost:5173',
			reuseExistingServer: !process.env.CI,
			timeout: 60_000
		}
	]
});
