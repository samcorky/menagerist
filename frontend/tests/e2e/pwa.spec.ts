import { test, expect } from './fixtures';

/**
 * Asks Chromium itself whether the app can be installed: the manifest parses without errors
 * and no installability criterion fails. It reads the same checks the browser's install button
 * and Lighthouse use. (Android and iOS still need trying on a real device.)
 */
test('serves a web app manifest and its icons with the right types', async ({ request }) => {
	const manifest = await request.get('/manifest.webmanifest');
	expect(manifest.status()).toBe(200);
	expect(manifest.headers()['content-type']).toContain('application/manifest+json');

	const { icons } = (await manifest.json()) as { icons: { src: string }[] };
	for (const { src } of icons) {
		const icon = await request.get(src);
		expect(icon.status(), src).toBe(200);
		expect(icon.headers()['content-type'], src).toBe('image/png');
	}
	expect((await request.get('/apple-touch-icon.png')).status()).toBe(200);
});

test('the browser reads the manifest without errors and finds the app installable', async ({
	page
}) => {
	await page.goto('/');
	await expect(page.getByRole('link', { name: 'Home', exact: true }).first()).toBeVisible();

	const cdp = await page.context().newCDPSession(page);
	const { errors, data } = await cdp.send('Page.getAppManifest');
	expect(errors, 'manifest problems').toEqual([]);
	expect(JSON.parse(data ?? '{}')).toMatchObject({ id: '/', scope: '/', display: 'standalone' });

	const { installabilityErrors } = await cdp.send('Page.getInstallabilityErrors');
	expect(installabilityErrors.map((e) => e.errorId)).toEqual([]);
});

test('the theme colour follows the theme the person picks', async ({ page }) => {
	await page.goto('/');
	const colour = page.locator('meta[name="theme-color"]');

	await page.evaluate(() => localStorage.setItem('theme', 'dark'));
	await page.reload();
	await expect(colour).toHaveAttribute('content', '#0a0a0a');

	await page.evaluate(() => localStorage.setItem('theme', 'light'));
	await page.reload();
	await expect(colour).toHaveAttribute('content', '#ffffff');
});

test('a launch with no connection starts the real app, and the cache holds nothing private', async ({
	page,
	context
}) => {
	const home = page.getByRole('link', { name: 'Home', exact: true }).first();
	await page.goto('/');
	await expect(home).toBeVisible();
	await expect
		.poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null), {
			message: 'the worker takes control of the page'
		})
		.toBe(true);

	// Cache Storage holds the build's files, the app shell and the last-resort offline page, and
	// no API response, account page or media.
	const cached = await page.evaluate(async () => {
		const paths: string[] = [];
		for (const name of await caches.keys()) {
			for (const request of await (await caches.open(name)).keys()) {
				paths.push(new URL(request.url).pathname);
			}
		}
		return paths;
	});
	expect(cached).toContain('/200.html');
	expect(cached).toContain('/offline.html');
	const shellFiles = ['/200.html', '/offline.html'];
	expect(cached.filter((p) => !p.startsWith('/_app/') && !shellFiles.includes(p))).toEqual([]);

	// The shell boots the real app, which shows its own offline screen rather than a login
	// redirect or the hand-written page, and loads the page by itself once the connection returns.
	await context.setOffline(true);
	await page.goto('/items');
	await expect(page.getByTestId('start-offline')).toContainText("You're offline");
	await expect(page).toHaveURL(/\/items$/);

	await context.setOffline(false);
	await expect(page.getByRole('heading', { name: 'My items', level: 1 })).toBeVisible();
	await expect(page.getByTestId('start-offline')).toHaveCount(0);
});

test('the service worker script is revalidated, not cached for an hour', async ({ request }) => {
	const worker = await request.get('/service-worker.js');
	expect(worker.status()).toBe(200);
	expect(worker.headers()['cache-control']).toBe('no-cache');
});
