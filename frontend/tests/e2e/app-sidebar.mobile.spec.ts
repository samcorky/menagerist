import { test, expect } from './fixtures';

/** On a phone the top bar must fit the screen, and the burger reaches the whole sidebar. */
for (const path of ['/', '/items', '/settings']) {
	test(`${path} does not scroll sideways`, async ({ page }) => {
		await page.goto(path);
		await expect(page.getByRole('button', { name: 'Menu', exact: true })).toBeVisible();
		const overflow = await page.evaluate(
			() => document.documentElement.scrollWidth - window.innerWidth
		);
		expect(overflow).toBeLessThanOrEqual(0);
	});
}

test('the burger opens the drawer with every section and a touch-sized close target', async ({
	page
}) => {
	await page.goto('/');
	await page.getByRole('button', { name: 'Menu', exact: true }).tap();
	const nav = page.getByRole('navigation', { name: 'Main', exact: true });
	await expect(nav).toBeVisible();
	for (const name of ['Home', 'Items', 'Collections', 'Item types', 'Account', 'Settings']) {
		await expect(nav.getByRole('link', { name, exact: true })).toBeVisible();
	}
	const box = await nav.getByRole('link', { name: 'Collections', exact: true }).boundingBox();
	expect(box?.height).toBeGreaterThanOrEqual(44);
	await nav.getByRole('link', { name: 'Collections', exact: true }).tap();
	await expect(page).toHaveURL(/\/collections$/);
	await expect(nav).toBeHidden();
});

test('the page behind the open drawer cannot scroll', async ({ page }) => {
	await page.goto('/');
	const scroller = page.locator('#main-scroll');
	await expect(scroller).toHaveCSS('overflow-y', 'auto');

	await page.getByRole('button', { name: 'Menu', exact: true }).tap();
	await expect(page.getByRole('dialog')).toBeVisible();
	await expect(scroller).toHaveCSS('overflow-y', 'hidden');

	await page.keyboard.press('Escape');
	await expect(page.getByRole('dialog')).toHaveCount(0);
	await expect(scroller).toHaveCSS('overflow-y', 'auto');
});
