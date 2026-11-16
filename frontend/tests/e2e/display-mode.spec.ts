import type { BrowserContext, Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { createUserViaApi, skipDeviceNamePrompt } from './helpers';

/**
 * Chromium cannot emulate `display-mode` (CDP's `setEmulatedMedia` ignores it), so the page's
 * `matchMedia` answers that one query from a switch the test flips; every other query is real.
 */
async function emulateDisplayMode(context: BrowserContext, standalone: boolean): Promise<void> {
	await context.addInitScript((initial: boolean) => {
		const query = '(display-mode: standalone)';
		const real = window.matchMedia.bind(window);
		const listeners = new Set<(event: { matches: boolean }) => void>();
		let matches = initial;
		const list = {
			media: query,
			onchange: null,
			get matches() {
				return matches;
			},
			addEventListener: (_: string, listener: (event: { matches: boolean }) => void) =>
				listeners.add(listener),
			removeEventListener: (_: string, listener: (event: { matches: boolean }) => void) =>
				listeners.delete(listener),
			dispatchEvent: () => true
		};
		window.matchMedia = ((q: string) =>
			q === query ? (list as unknown as MediaQueryList) : real(q)) as typeof window.matchMedia;
		(window as unknown as { setStandalone: (value: boolean) => void }).setStandalone = (value) => {
			matches = value;
			for (const listener of listeners) listener({ matches: value });
		};
	}, standalone);
}

/** Collects the display mode each API request reported. */
function recordModes(page: Page): string[] {
	const modes: string[] = [];
	page.on('request', (request) => {
		if (new URL(request.url()).pathname.startsWith('/api/')) {
			modes.push(request.headers()['x-client-display-mode'] ?? 'none');
		}
	});
	return modes;
}

test('a browser tab reports the browser display mode', async ({ page }) => {
	const modes = recordModes(page);

	await page.goto('/');
	await expect(page.getByRole('link', { name: 'Home', exact: true }).first()).toBeVisible();

	expect(modes.length).toBeGreaterThan(0);
	expect(new Set(modes)).toEqual(new Set(['browser']));
});

test('signing in from the installed app is shown on the devices list, and changes are followed', async ({
	browser,
	request,
	workerBaseURL
}) => {
	const user = await createUserViaApi(request, workerBaseURL, { prefix: 'installed' });
	const context = await browser.newContext({
		baseURL: workerBaseURL,
		storageState: { cookies: [], origins: [] },
		extraHTTPHeaders: {}
	});
	await emulateDisplayMode(context, true);
	const page = await context.newPage();
	const modes = recordModes(page);

	await page.goto('/login');
	await page.getByLabel('Username').fill(user.username);
	await page.getByLabel('Password', { exact: true }).fill(user.password);
	await skipDeviceNamePrompt(page);
	await page.getByRole('button', { name: 'Sign in', exact: true }).click();
	await expect(page.getByRole('link', { name: 'Home', exact: true }).first()).toBeVisible();
	expect(new Set(modes)).toEqual(new Set(['standalone']));

	await page.goto('/settings/account');
	const devices = page.getByRole('heading', { name: 'Devices' }).locator('xpath=ancestor::section');
	await expect(devices.getByText(/^App on .+ \(.+\)$/)).toBeVisible();
	await expect(devices.getByText('This device')).toBeVisible();

	// Leaving the installed window (for example opening the app in a tab) applies at once.
	modes.length = 0;
	await page.evaluate(() =>
		(window as unknown as { setStandalone: (value: boolean) => void }).setStandalone(false)
	);
	await page.getByRole('link', { name: 'Home', exact: true }).first().click();
	await expect.poll(() => modes.length).toBeGreaterThan(0);
	expect(new Set(modes)).toEqual(new Set(['browser']));

	await context.close();
});
