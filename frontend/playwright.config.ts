import { defineConfig, devices } from '@playwright/test';

const E2E_DATABASE_URL = 'postgresql+asyncpg://menagerist:menagerist@localhost:55433/menagerist';

// Deliberately not the dev ports (8000/5173): the suite starts its own
// servers wired to the throwaway e2e database, and must never reuse - or
// collide with - a dev or deployed stack running on the defaults.
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8100);
const FRONTEND_PORT = Number(process.env.E2E_FRONTEND_PORT ?? 5273);

// Set via `poe test-e2e-slow` so a headed run is actually watchable: delays
// every Playwright action by this many milliseconds. The default test
// timeout would otherwise be eaten by the added delay, so it's extended too.
const slowMo = process.env.PW_SLOWMO ? Number(process.env.PW_SLOWMO) : undefined;

export default defineConfig({
	testDir: './tests/e2e',
	// A single shared dev backend/frontend/database backs every worker (no
	// per-worker isolation), so parallel workers cause real contention and
	// timeouts under load rather than exercising independent state.
	fullyParallel: false,
	workers: 1,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 1 : 0,
	reporter: 'list',
	// Vite compiles pages on first visit and the servers restart every run, so
	// multi-step specs in a cold run need more than Playwright's 30s default.
	timeout: slowMo ? 90_000 : 60_000,
	expect: { timeout: 10_000 },
	use: {
		baseURL: `http://localhost:${FRONTEND_PORT}`,
		trace: 'on-first-retry',
		launchOptions: { slowMo }
	},
	projects: [
		{
			name: 'chromium',
			use: { ...devices['Desktop Chrome'] }
		}
	],
	webServer: [
		{
			command: `uv run menagerist serve --host 127.0.0.1 --port ${BACKEND_PORT}`,
			cwd: '..',
			env: { MENAGERIST_DATABASE_URL: E2E_DATABASE_URL },
			url: `http://localhost:${BACKEND_PORT}/api/health/ready`,
			reuseExistingServer: !process.env.CI,
			timeout: 60_000
		},
		{
			command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
			cwd: '.',
			env: { MENAGERIST_API_PROXY_TARGET: `http://localhost:${BACKEND_PORT}` },
			url: `http://localhost:${FRONTEND_PORT}`,
			reuseExistingServer: !process.env.CI,
			timeout: 60_000
		}
	]
});
