import { test, expect } from './fixtures';

/**
 * The last-resort page the service worker serves picks its mark and wording from the browser, and
 * leaves for the app once the server answers.
 */
test('says the server is not answering when the browser is online but the server is not', async ({
	page
}) => {
	await page.route('**/api/health', (route) => route.abort('connectionrefused'));
	await page.goto('/offline.html');

	await expect(page.getByRole('heading', { name: "Can't reach Menagerist" })).toBeVisible();
	await expect(page.getByText("The server isn't answering.")).toBeVisible();
	await expect(page.locator('[data-icon="server-off"]')).toBeVisible();
	await expect(page.locator('[data-icon="wifi-off"]')).toBeHidden();
	// Its own style is applied, not blocked by the policy it is served with.
	await expect(page.locator('[data-icon="server-off"]')).toHaveCSS('width', '48px');
});

test('says you are offline when the browser has no connection', async ({ page }) => {
	await page.addInitScript(() => {
		Object.defineProperty(navigator, 'onLine', { get: () => false });
	});
	await page.goto('/offline.html');

	await expect(page.getByRole('heading', { name: "You're offline" })).toBeVisible();
	await expect(page.getByText('Check your connection, then try again.')).toBeVisible();
	await expect(page.locator('[data-icon="wifi-off"]')).toBeVisible();
	await expect(page.locator('[data-icon="server-off"]')).toBeHidden();
	await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
});

test('goes to the app when it is opened while the server is answering', async ({ page }) => {
	await page.goto('/offline.html');

	await expect(page).not.toHaveURL(/offline\.html/);
	await expect(page.getByRole('link', { name: 'Home', exact: true }).first()).toBeVisible();
});

test('goes to the app by itself once the server is back', async ({ page }) => {
	await page.route('**/api/health', (route) => route.abort('connectionrefused'));
	await page.goto('/offline.html');
	await expect(page.getByRole('heading', { name: "Can't reach Menagerist" })).toBeVisible();

	await page.unroute('**/api/health');

	await expect(page).not.toHaveURL(/offline\.html/, { timeout: 15_000 });
});
