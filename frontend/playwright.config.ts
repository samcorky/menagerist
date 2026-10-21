import { mkdirSync } from 'node:fs';
import { availableParallelism, tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

// Keep the suite off the dev ports to avoid clashing with local stacks.
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8100);

// Auth tests run against a dedicated backend and empty database.
const AUTH_BACKEND_PORT = Number(process.env.E2E_AUTH_BACKEND_PORT ?? 8190);

// Cookie specs run on their own backend behind a TLS proxy, in WebKit and Firefox as well.
// `E2E_COOKIES=1` (set by `poe test-e2e-cookies`) swaps the whole suite for just those.
const COOKIES = process.env.E2E_COOKIES === '1';
const COOKIES_BACKEND_PORT = Number(process.env.E2E_COOKIES_BACKEND_PORT ?? 8191);
const COOKIES_TLS_PORT = Number(process.env.E2E_COOKIES_TLS_PORT ?? 8192);

// Use the configured worker count, or fall back to the machine core count.
const WORKERS = Number(process.env.E2E_WORKERS) || availableParallelism();

// Use the production build served by each backend.
const FRONTEND_DIST = fileURLToPath(new URL('./build', import.meta.url));

// A slow-motion run is easier to watch, so extend the timeout too.
const slowMo = process.env.PW_SLOWMO ? Number(process.env.PW_SLOWMO) : undefined;

/**
 * A backend on `port` serving the built SPA from the database menagerist_{name}.
 * `--no-sync` avoids Windows lock clashes while backends start together.
 */
function backend(port: number, name: string, extraEnv: Record<string, string> = {}) {
	const backupPath = join(tmpdir(), `menagerist-e2e-backups-${name}`);
	mkdirSync(backupPath, { recursive: true });

	return {
		command: `uv run --no-sync menagerist serve --host 127.0.0.1 --port ${port}`,
		cwd: '..',
		env: {
			MENAGERIST_DATABASE_URL: `postgresql+asyncpg://menagerist:menagerist@localhost:55433/menagerist_${name}`,
			MENAGERIST_FRONTEND_DIST_PATH: FRONTEND_DIST,
			// Example covers are stored as media, so each backend needs a writable directory.
			MENAGERIST_MEDIA_STORAGE_PATH: join(tmpdir(), `menagerist-e2e-media-${name}`),
			MENAGERIST_BACKUP_PATH: backupPath,
			MENAGERIST_BACKUP_BEFORE_MIGRATE: 'false',
			...extraEnv
		},
		url: `http://localhost:${port}/api/health/ready`,
		reuseExistingServer: !process.env.CI,
		timeout: 60_000
	};
}

// The cookie backend is reached directly over HTTP and, through the proxy, over HTTPS. Trusting
// the proxy's address makes the app see the proxied requests as HTTPS, so one backend issues
// both the `__Host-Http-` and the plain cookie name.
const cookieServers = [
	backend(COOKIES_BACKEND_PORT, 'cookies', { MENAGERIST_TRUSTED_PROXIES: '127.0.0.1' }),
	{
		command: `node tests/e2e/tls-proxy.mjs ${COOKIES_TLS_PORT} ${COOKIES_BACKEND_PORT}`,
		url: `https://localhost:${COOKIES_TLS_PORT}/api/health/ready`,
		ignoreHTTPSErrors: true,
		reuseExistingServer: !process.env.CI,
		timeout: 30_000
	}
];

// Playwright's WebKit is an engine build, not Safari itself. Use these as a regression guard
// and still check by hand in Safari on macOS and iOS before a release.
const cookieProject = (name: string, device: string) => ({
	name,
	use: {
		...devices[device],
		baseURL: `https://localhost:${COOKIES_TLS_PORT}`,
		ignoreHTTPSErrors: true
	},
	testMatch: '**/cookies.spec.ts',
	dependencies: ['cookies-setup']
});
const cookieProjects = [
	{
		name: 'cookies-setup',
		use: { ...devices['Desktop Chrome'] },
		testMatch: '**/cookies.setup.ts'
	},
	cookieProject('cookies-chromium', 'Desktop Chrome'),
	cookieProject('cookies-webkit', 'Desktop Safari'),
	cookieProject('cookies-firefox', 'Desktop Firefox')
];

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
	projects: COOKIES
		? cookieProjects
		: [
				{
					name: 'chromium',
					use: { ...devices['Desktop Chrome'] },
					testIgnore: ['**/*.mobile.spec.ts', '**/auth.spec.ts', '**/cookies.*']
				},
				// Phone-sized run of the viewport-agnostic specs plus the *.mobile.spec.ts layout checks.
				{
					name: 'mobile',
					use: { ...devices['Pixel 5'], viewport: { width: 360, height: 740 } },
					testMatch: [
						'**/backups.spec.ts',
						'**/collections.spec.ts',
						'**/create-item.spec.ts',
						'**/connect-items.spec.ts',
						'**/quick-capture.spec.ts',
						'**/*.mobile.spec.ts'
					]
				},
				// First-run setup and sign-in flows against the dedicated empty database; runs serially.
				{
					name: 'auth',
					use: { ...devices['Desktop Chrome'], baseURL: `http://localhost:${AUTH_BACKEND_PORT}` },
					testMatch: '**/auth.spec.ts'
				}
			],
	webServer: COOKIES
		? cookieServers
		: [
				...Array.from({ length: WORKERS }, (_, i) => backend(BACKEND_PORT + i, `w${i}`)),
				backend(AUTH_BACKEND_PORT, 'auth')
			]
});
