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
