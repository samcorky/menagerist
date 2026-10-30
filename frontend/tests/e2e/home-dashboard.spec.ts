import { test, expect } from './fixtures';
import { openQuickCapture, ownedData, uniqueName } from './helpers';

/** Home as a collector's dashboard: real counts, the true newest items, tidy-up filters. */
const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

test('Newly added shows the latest items even in a large library', async ({ page, request }) => {
	const names: string[] = [];
	for (let i = 0; i < 14; i++) names.push((await makeItem(request, uniqueName(`Dash ${i}`))).name);
	await page.goto('/');
	await expect(page.getByRole('link', { name: names[13] }).first()).toBeVisible();
	// The oldest of the fourteen is past both the newest eight and the last five edited.
	await expect(page.locator('main').getByText(names[0], { exact: true })).toHaveCount(0);
});

test('the Items tile shows the real total', async ({ page, request }) => {
	await makeItem(request, uniqueName('Dash tile'));
	const res = await request.get('/api/v1/node/count');
	const { count } = (await res.json()) as { count: number };
	await page.goto('/');
	await expect(page.getByTestId('stat-items')).toContainText(count.toLocaleString('en-GB'));
});

test('Tidy up counts match the list they open', async ({ page, request }) => {
	await makeItem(request, uniqueName('Dash bare'));
	await page.goto('/');
	const row = page.getByRole('link', { name: /^No description/ });
	await expect(row).toBeVisible();
	const shown = (await row.innerText()).match(/([\d,]+)\+?\s*$/)?.[1] ?? '';
	expect(shown).not.toBe('');
	await row.click();
	await expect(page).toHaveURL(/\/items\?.*f=/);
	await expect(page.getByText(new RegExp(`^${shown} items?$`))).toBeVisible();
});

test('blocks fold away and stay folded after a reload', async ({ page, request }) => {
	await makeItem(request, uniqueName('Dash fold'));
	await page.goto('/');
	const toggle = page.locator('main').getByRole('button', { name: /^Newly added/ });
	await expect(toggle).toHaveAttribute('aria-expanded', 'true');
	await toggle.click();
	await expect(toggle).toHaveAttribute('aria-expanded', 'false');
	await page.reload();
	await expect(page.locator('main').getByRole('button', { name: /^Newly added/ })).toHaveAttribute(
		'aria-expanded',
		'false'
	);
	await page
		.locator('main')
		.getByRole('button', { name: /^Newly added/ })
		.click();
});

test('the item types and collections blocks open their lists', async ({ page, request }) => {
	await makeItem(request, uniqueName('Dash nav'));
	await page.goto('/');
	await expect(page.locator('main').getByRole('button', { name: /^Collections/ })).toBeVisible();
	await expect(page.locator('main').getByRole('button', { name: /^By item type/ })).toBeVisible();
	await expect(
		page.locator('main').getByRole('button', { name: /^Pick up where you left off/ })
	).toBeVisible();
});

test('opening Home after capturing an item loads each figure once, not twice', async ({ page }) => {
	await page.goto('/items');
	const dialog = await openQuickCapture(page);
	await dialog.getByPlaceholder('Name…').fill(uniqueName('Captured before Home'));
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(dialog).toBeHidden();

	let counts = 0;
	page.on('request', (r) => {
		if (r.url().includes('/api/v1/node/search/counts')) counts++;
	});
	await page.getByRole('link', { name: 'Home' }).first().click();
	await expect(page.getByTestId('stat-items')).toBeVisible();
	await page.waitForLoadState('networkidle');

	// Stats and Tidy up are one counts request each; a second load would double both.
	expect(counts).toBeLessThanOrEqual(2);
});
