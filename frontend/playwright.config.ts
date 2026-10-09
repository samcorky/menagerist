import { availableParallelism, tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

// Deliberately not the dev ports (8000/5173): the suite starts its own
// servers wired to throwaway databases, and must never reuse - or collide
// with - a dev or deployed stack running on the defaults. Worker i uses
// BACKEND_PORT + i and the database menagerist_w{i} (see scripts/e2e_migrate.py).
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8100);

// `poe test-e2e --workers N` exports E2E_WORKERS; a bare `npx playwright test` falls back to the core count.
const WORKERS = Number(process.env.E2E_WORKERS) || availableParallelism();

// Production build served by each backend (`poe e2e-build`).
const FRONTEND_DIST = fileURLToPath(new URL('./build', import.meta.url));

// Set via `poe test-e2e-slow` so a headed run is actually watchable: delays
// every Playwright action by this many milliseconds. The default test
// timeout would otherwise be eaten by the added delay, so it's extended too.
const slowMo = process.env.PW_SLOWMO ? Number(process.env.PW_SLOWMO) : undefined;

export default defineConfig({
	testDir: './tests/e2e',
	// Files run in parallel across workers, each with its own backend and
	// database; tests inside a file stay ordered.
	fullyParallel: false,
	workers: WORKERS,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 1 : 0,
	reporter: 'list',
	// Backends restart every run and workers share the CPU, so
	// multi-step specs need more than Playwright's 30s default.
	timeout: slowMo ? 90_000 : 60_000,
	expect: { timeout: 10_000 },
	use: {
		trace: 'on-first-retry',
		launchOptions: { slowMo }
	},
	projects: [
		{
			name: 'chromium',
			use: { ...devices['Desktop Chrome'] },
			testIgnore: '**/*.mobile.spec.ts'
		},
		// Phone-sized run of the viewport-agnostic specs plus the *.mobile.spec.ts layout checks.
		{
			name: 'mobile',
			use: { ...devices['Pixel 5'], viewport: { width: 360, height: 740 } },
			testMatch: [
				'**/collections.spec.ts',
				'**/create-item.spec.ts',
				'**/connect-items.spec.ts',
				'**/quick-capture.spec.ts',
				'**/*.mobile.spec.ts'
			]
		}
	],
	webServer: Array.from({ length: WORKERS }, (_, i) => ({
		command: `uv run menagerist serve --host 127.0.0.1 --port ${BACKEND_PORT + i}`,
		cwd: '..',
		env: {
			MENAGERIST_DATABASE_URL: `postgresql+asyncpg://menagerist:menagerist@localhost:55433/menagerist_w${i}`,
			MENAGERIST_FRONTEND_DIST_PATH: FRONTEND_DIST,
			// Example covers are stored as media, so each backend needs a writable directory.
			MENAGERIST_MEDIA_STORAGE_PATH: join(tmpdir(), `menagerist-e2e-media-w${i}`)
		},
		url: `http://localhost:${BACKEND_PORT + i}/api/health/ready`,
		reuseExistingServer: !process.env.CI,
		timeout: 60_000
	}))
});
