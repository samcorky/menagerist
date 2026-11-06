import { test, expect, type Page } from './fixtures';

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

test('Home shows that it is offline, and loads again from the banner Retry', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('link', { name: 'Home', exact: true }).first()).toBeVisible();

	await page.getByRole('link', { name: 'Items', exact: true }).first().click();
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
