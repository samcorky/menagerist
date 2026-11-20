import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** Install guidance: a Home card and a Settings page, native where the browser offers it. */
const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const IPHONE_SAFARI =
	'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1';

/** Fires what Chromium fires when the app can be installed; headless Chromium never does. */
async function offerNativeInstall(page: Page) {
	await expect(page.getByRole('link', { name: 'Home', exact: true })).toBeVisible();
	await page.evaluate(() => {
		const event = new Event('beforeinstallprompt', { cancelable: true }) as Event & {
			prompt: () => Promise<void>;
			userChoice: Promise<{ outcome: string }>;
		};
		event.prompt = async () => {
			(window as unknown as { installPrompted: number }).installPrompted =
				((window as unknown as { installPrompted?: number }).installPrompted ?? 0) + 1;
		};
		event.userChoice = Promise.resolve({ outcome: 'dismissed' });
		window.dispatchEvent(event);
	});
}

test('Home offers the browser install prompt, and Install shows it', async ({ page, request }) => {
	await makeItem(request, uniqueName('Install home'));
	await page.goto('/');
	await expect(page.getByTestId('install-card')).toHaveCount(0);

	await offerNativeInstall(page);
	const card = page.getByTestId('install-card');
	await expect(card).toBeVisible();
	await card.getByRole('button', { name: 'Install' }).click();

	await expect
		.poll(() =>
			page.evaluate(() => (window as unknown as { installPrompted?: number }).installPrompted)
		)
		.toBe(1);
	// The kept event can be shown once, so the card has nothing left to offer.
	await expect(card).toHaveCount(0);
});

test('dismissing the Home card keeps it away on this device', async ({ page, request }) => {
	await makeItem(request, uniqueName('Install dismiss'));
	await page.goto('/');
	await offerNativeInstall(page);
	await page.getByTestId('install-card').getByRole('button', { name: 'Dismiss' }).click();
	await expect(page.getByTestId('install-card')).toHaveCount(0);

	await page.reload();
	await offerNativeInstall(page);
	await expect(page.getByTestId('install-card')).toHaveCount(0);
});

test.describe('Safari on an iPhone, which has no install prompt', () => {
	test.use({ userAgent: IPHONE_SAFARI });

	test('the Home card opens the steps for Add to Home Screen', async ({ page, request }) => {
		await makeItem(request, uniqueName('Install ios'));
		await page.goto('/');
		await page.getByTestId('install-card').getByRole('button', { name: 'How to install' }).click();

		const steps = page
			.getByRole('dialog', { name: 'Install the app' })
			.getByTestId('install-steps');
		await expect(steps).toContainText('Add to Home Screen');
	});

	test('the Settings page shows the same steps', async ({ page }) => {
		await page.goto('/settings/install');
		await expect(page.getByTestId('install-panel').getByTestId('install-steps')).toContainText(
			'Add to Home Screen'
		);
	});
});

test('Settings lists Install the app, and says when a browser cannot install', async ({ page }) => {
	await page.goto('/settings');
	await page
		.getByRole('link', { name: /Install the app/ })
		.first()
		.click();
	await expect(page).toHaveURL(/\/settings\/install$/);
	await expect(page.getByTestId('install-panel')).toContainText("can't install the app");
});

test('after Install the Settings page never says the browser cannot install', async ({ page }) => {
	await page.goto('/settings/install');
	await offerNativeInstall(page);
	const panel = page.getByTestId('install-panel');
	await panel.getByRole('button', { name: 'Install' }).click();

	// The browser reported the prompt closed, which is not the same as being unable to install.
	await expect(panel).toContainText('You closed the install prompt');
	await expect(panel).not.toContainText("can't install the app");
});

test('the Settings page offers the native Install button when the browser does', async ({
	page
}) => {
	await page.goto('/settings/install');
	await offerNativeInstall(page);
	await expect(
		page.getByTestId('install-panel').getByRole('button', { name: 'Install' })
	).toBeVisible();
});
