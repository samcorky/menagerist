import { test, expect, request, apiSessionOptions, type Page } from './fixtures';
import { asUser, createUserViaApi } from './helpers';

/** Every API call fails the way it does with no connection: `fetch` rejects with no response. */
async function cutApi(page: Page) {
	await page.route('**/api/**', (route) => route.abort('internetdisconnected'));
}

async function restoreApi(page: Page) {
	await page.unroute('**/api/**');
}

for (const { path, link, what, emptyText } of [
	{ path: '/items', link: 'Items', what: 'your items', emptyText: 'Nothing here yet' },
	{
		path: '/collections',
		link: 'Collections',
		what: 'your collections',
		emptyText: 'No collections yet'
	}
]) {
	test(`${path} says it cannot load when offline, never that there is nothing`, async ({
		page
	}) => {
		await page.goto('/');
		await expect(page.getByRole('link', { name: 'Home', exact: true }).first()).toBeVisible();

		// Navigate inside the app: the sign-in check has already passed, so only the page's own data fails.
		await cutApi(page);
		await page.getByRole('link', { name: link, exact: true }).first().click();

		const failed = page.getByTestId('load-failed');
		await expect(failed).toContainText(`You're offline, so ${what} can't load.`);
		await expect(page.getByTestId('offline-banner')).toBeVisible();
		await expect(page.getByText(emptyText)).toHaveCount(0);

		await restoreApi(page);
		await failed.getByRole('button', { name: 'Try again' }).click();
		await expect(failed).toHaveCount(0);
		await expect(page.getByTestId('offline-banner')).toHaveCount(0);
	});
}

// Pages not in the sidebar are opened online first, then reached again with Back while offline,
// which navigates inside the app the same way a link would. Recovery fires the browser's `online`
// event, as a real reconnect does, rather than racing a background request that may clear the
// banner first.
for (const { path, heading, what, emptyText } of [
	{
		path: '/admin/devices',
		heading: 'Devices',
		what: ['the active devices'],
		emptyText: 'No active devices'
	},
	{ path: '/admin/users', heading: 'Users', what: ['the accounts'], emptyText: null },
	{
		path: '/admin/backups',
		heading: 'Backups',
		what: ['the backups'],
		emptyText: 'No backups yet'
	},
	{
		path: '/library/item-types',
		heading: 'Item types',
		what: ['your item types'],
		emptyText: 'No item types yet'
	},
	{
		path: '/library/connection-types',
		heading: 'Connection types',
		what: ['your connection types'],
		emptyText: 'No relationship types yet'
	},
	{
		path: '/library/saved-fields',
		heading: 'Saved fields',
		what: ['your saved fields', 'your saved lists', 'your saved field groups'],
		emptyText: 'No saved fields yet'
	}
]) {
	test(`${path} says it cannot load when offline, and loads again once back online`, async ({
		page
	}) => {
		await page.goto(path);
		await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
		await page.getByRole('link', { name: 'Home', exact: true }).first().click();
		// Wait for Home to render, not just the address to change: Back during a navigation is lost.
		await expect(page).toHaveURL(/\/$/);
		await expect(page.getByRole('heading', { name: heading, exact: true })).toHaveCount(0);

		await cutApi(page);
		await page.goBack();
		await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();

		const failed = page.getByTestId('load-failed');
		for (const name of what) {
			await expect(
				failed.filter({ hasText: `You're offline, so ${name} can't load.` })
			).toBeVisible();
		}
		if (emptyText) await expect(page.getByText(emptyText)).toHaveCount(0);
		const banner = page.getByTestId('offline-banner');
		await expect(banner).toBeVisible();

		await restoreApi(page);
		await page.evaluate(() => window.dispatchEvent(new Event('online')));
		await expect(failed).toHaveCount(0);
		await expect(banner).toHaveCount(0);
	});
}

test('a failed refresh keeps the devices already shown', async ({
	page,
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const member = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'offline-dev-member' });
	await adminApi.dispose();
	const memberSession = await asUser(browser, member);

	await page.goto('/admin/devices');
	const memberRow = page.locator('tr, li').filter({ hasText: member.displayName }).first();
	await expect(memberRow).toBeVisible();

	// Signing out succeeds, but the list reload after it cannot reach the server.
	await page.route('**/api/**', (route) =>
		route.request().method() === 'GET' ? route.abort('internetdisconnected') : route.continue()
	);
	await memberRow.getByRole('button', { name: 'Sign out' }).click();
	await expect(page.getByText('Device signed out')).toBeVisible();
	await expect(page.getByText('You appear to be offline')).toBeVisible();
	await expect(page.getByTestId('load-failed')).toHaveCount(0);
	await expect(memberRow).toBeVisible();

	await restoreApi(page);
	await page.evaluate(() => window.dispatchEvent(new Event('online')));
	await expect(memberRow).toHaveCount(0);

	await memberSession.context.close();
});

test('Home shows that it is offline, and loads again from the banner Retry', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('link', { name: 'Home', exact: true }).first()).toBeVisible();

	await page.getByRole('link', { name: 'Items', exact: true }).first().click();
	await expect(page.getByPlaceholder('Search your items…')).toBeVisible();
	await cutApi(page);
	await page.getByRole('link', { name: 'Home', exact: true }).first().click();
	await expect(page.getByText("You're offline, so your totals can't load.")).toBeVisible();
	const banner = page.getByTestId('offline-banner');
	await expect(banner).toBeVisible();

	await restoreApi(page);
	await banner.getByRole('button', { name: 'Retry' }).click();
	await expect(page.getByText("You're offline, so your totals can't load.")).toHaveCount(0);
	await expect(banner).toHaveCount(0);
});

test('Home never shows blank counts when the browser itself goes offline', async ({
	page,
	context
}) => {
	await page.goto('/');
	await expect(page.getByRole('link', { name: 'Home', exact: true }).first()).toBeVisible();
	await page.getByRole('link', { name: 'Items', exact: true }).first().click();
	await expect(page.getByPlaceholder('Search your items…')).toBeVisible();

	await context.setOffline(true);
	await page.getByRole('link', { name: 'Home', exact: true }).first().click();

	await expect(page.getByTestId('offline-banner')).toBeVisible();
	await expect(page.getByText("You're offline, so your totals can't load.")).toBeVisible();
	await expect(page.getByText("You don't have any items yet")).toHaveCount(0);

	// Coming back online reloads the failed blocks without a tap.
	await context.setOffline(false);
	await expect(page.getByText("You're offline, so your totals can't load.")).toHaveCount(0);
	await expect(page.getByTestId('offline-banner')).toHaveCount(0);
});
