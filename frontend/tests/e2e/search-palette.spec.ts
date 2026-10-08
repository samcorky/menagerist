import { test, expect, type Page } from './fixtures';
import { ownedData, removeExamplePacks, uniqueName } from './helpers';

/** The global search popup: opened by `/` or the header button, driven from the keyboard. */
const { makeItem, makeItemType, cleanUp } = ownedData();

test.afterEach(async ({ request }) => {
	await cleanUp(request);
	await removeExamplePacks(request);
});

const popup = (page: Page) => page.getByRole('dialog', { name: 'Search items' });
const input = (page: Page) => popup(page).getByPlaceholder('Search your items…');

async function openWithSlash(page: Page, path = '/') {
	await page.goto(path);
	await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
	await page.keyboard.press('/');
	await expect(popup(page)).toBeVisible();
}

test('/ opens the popup with the input focused and a hint', async ({ page }) => {
	await openWithSlash(page);
	await expect(input(page)).toBeFocused();
	await expect(popup(page).getByText('Type to search your items')).toBeVisible();
});

test('typing finds an item with its type, and Enter opens it', async ({ page, request }) => {
	const type = await makeItemType(request, uniqueName('Gadget kind'));
	const item = await makeItem(request, uniqueName('Searchable gizmo'), type.slug);

	await openWithSlash(page);
	await input(page).fill(item.name);
	const row = popup(page).getByRole('option', { name: new RegExp(item.name) });
	await expect(row).toBeVisible();
	await expect(row).toContainText(type.label);

	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(new RegExp(`/items/${item.id}$`));
	await expect(popup(page)).toBeHidden();
	// Navigating away leaves focus on the body, not on the header button.
	await expect(page.locator('body')).toBeFocused();
});

test('arrow keys move the highlight and Enter opens the second result', async ({
	page,
	request
}) => {
	const prefix = uniqueName('Arrow pair');
	const first = await makeItem(request, `${prefix} A`);
	const second = await makeItem(request, `${prefix} B`);

	await openWithSlash(page);
	await input(page).fill(prefix);
	const rowA = popup(page).getByRole('option', { name: new RegExp(`${prefix} A`) });
	const rowB = popup(page).getByRole('option', { name: new RegExp(`${prefix} B`) });
	await expect(rowA).toBeVisible();
	await expect(rowB).toBeVisible();
	const rows = await popup(page).getByRole('option').allInnerTexts();
	const order =
		rows.findIndex((t) => t.includes(`${prefix} A`)) <
		rows.findIndex((t) => t.includes(`${prefix} B`));
	const [top, bottom, bottomItem] = order ? [rowA, rowB, second] : [rowB, rowA, first];

	await expect(top).toHaveAttribute('aria-selected', 'true');
	await page.keyboard.press('ArrowDown');
	await expect(bottom).toHaveAttribute('aria-selected', 'true');
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(new RegExp(`/items/${bottomItem.id}$`));
});

test('a query with no match shows the empty state', async ({ page }) => {
	const query = `zzz-nothing-${Date.now()}`;
	await openWithSlash(page);
	await input(page).fill(query);
	// The text is also in a screen-reader status region, so target the visible copy.
	await expect(popup(page).getByRole('status')).toHaveText(`No items match "${query}"`);
	await expect(popup(page).locator('[aria-hidden="true"]', { hasText: query })).toBeVisible();
});

test('See all results opens the items page with the search pre-filled', async ({
	page,
	request
}) => {
	const item = await makeItem(request, uniqueName('Everything match'));

	await openWithSlash(page);
	await input(page).fill(item.name);
	await popup(page).getByRole('option', { name: 'See all results in Items' }).click();

	await expect(page).toHaveURL(/\/items\?q=/);
	await expect(page.getByPlaceholder('Search your items…')).toHaveValue(item.name);
	await expect(page.getByRole('link', { name: item.name }).first()).toBeVisible();
});

test('Esc closes the popup and returns focus to where it was', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
	const before = page.getByRole('link', { name: 'Items', exact: true }).first();
	await before.focus();
	await page.keyboard.press('/');
	await expect(popup(page)).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(popup(page)).toBeHidden();
	await expect(before).toBeFocused();
});

test('the desktop header Search items button opens the popup', async ({ page }) => {
	await page.goto('/');
	const button = page.getByRole('button', { name: 'Search items' });
	await button.click();
	await expect(popup(page)).toBeVisible();
	await expect(input(page)).toBeFocused();
	await page.keyboard.press('Escape');
	await expect(popup(page)).toBeHidden();
	await expect(button).toBeFocused();
});

test('example items carry the Example badge in results', async ({ page, request }) => {
	const res = await request.put('/api/v1/example/recipes/installation');
	expect(res.ok()).toBeTruthy();

	await openWithSlash(page);
	await input(page).fill('Mature cheddar');
	const row = popup(page).getByRole('option', { name: /^Mature cheddar/ });
	await expect(row).toBeVisible();
	await expect(row.getByText('Example', { exact: true })).toBeVisible();
});

test('n still opens quick capture, and / typed in the input is a character', async ({ page }) => {
	await openWithSlash(page);
	await input(page).pressSequentially('a/b');
	await expect(input(page)).toHaveValue('a/b');
	await expect(popup(page)).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(popup(page)).toBeHidden();

	await page.keyboard.press('n');
	await expect(page.getByRole('dialog', { name: 'Quick capture' })).toBeVisible();
});
