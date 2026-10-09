import { test, expect, type Page } from './fixtures';
import {
	failCollectionSearch,
	ownedData,
	removeExamplePacks,
	searchButton,
	uniqueName
} from './helpers';

/** The global search popup: opened by `/` or the header button, driven from the keyboard. */
const { makeItem, makeItemType, makeCollection, cleanUp } = ownedData();

test.afterEach(async ({ request }) => {
	await cleanUp(request);
	await removeExamplePacks(request);
});

const popup = (page: Page) => page.getByRole('dialog', { name: 'Search', exact: true });
const input = (page: Page) => popup(page).getByPlaceholder('Search everything…');

async function openWithSlash(page: Page, path = '/') {
	await page.goto(path);
	await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
	await page.keyboard.press('/');
	await expect(popup(page)).toBeVisible();
}

test('/ opens the popup with the input focused and a hint', async ({ page }) => {
	await openWithSlash(page);
	await expect(input(page)).toBeFocused();
	await expect(
		popup(page).getByText('Type to search items, collections, item types and pages')
	).toBeVisible();
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
	// Pages, collections and types add rows; only compare the two item rows' positions.
	const rows = await popup(page).getByRole('option').allInnerTexts();
	const order =
		rows.findIndex((t) => t.startsWith(`${prefix} A`)) <
		rows.findIndex((t) => t.startsWith(`${prefix} B`));
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
	await expect(popup(page).getByRole('status')).toHaveText(`Nothing found for "${query}"`);
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

test('the desktop header Search button opens the popup', async ({ page }) => {
	await page.goto('/');
	const button = searchButton(page);
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

// Grouped results: items, collections, item types and pages.

const row = (page: Page, text: string | RegExp) => popup(page).getByRole('option', { name: text });

test('a shared word shows Items, Collections and Item types in that order', async ({
	page,
	request
}) => {
	const token = uniqueName('Sharedword');
	const type = await makeItemType(request, `${token} kind`);
	const item = await makeItem(request, `${token} item`);
	const collection = await makeCollection(request, `${token} set`);

	await openWithSlash(page);
	await input(page).fill(token);
	await expect(row(page, new RegExp(collection.name))).toBeVisible();
	await expect(row(page, new RegExp(type.label))).toBeVisible();
	await expect(row(page, new RegExp(item.name))).toBeVisible();

	for (const heading of ['Items', 'Collections', 'Item types']) {
		await expect(popup(page).getByText(heading, { exact: true })).toBeVisible();
	}
	const texts = await popup(page).getByRole('option').allInnerTexts();
	const at = (needle: string) => texts.findIndex((t) => t.includes(needle));
	expect(at(item.name)).toBeGreaterThanOrEqual(0);
	expect(at(item.name)).toBeLessThan(at(collection.name));
	expect(at(collection.name)).toBeLessThan(at(type.label));
});

test('choosing an item, a collection and an item type each lands in the right place', async ({
	page,
	request
}) => {
	const token = uniqueName('Landword');
	const type = await makeItemType(request, `${token} kind`);
	const item = await makeItem(request, `${token} item`);
	const typed = await makeItem(request, uniqueName('Typed landing'), type.slug);
	const collection = await makeCollection(request, `${token} set`);

	await openWithSlash(page);
	await input(page).fill(token);
	await row(page, new RegExp(item.name)).click();
	await expect(page).toHaveURL(new RegExp(`/items/${item.id}$`));

	await openWithSlash(page);
	await input(page).fill(token);
	await row(page, new RegExp(collection.name)).click();
	await expect(page).toHaveURL(new RegExp(`/collections/${collection.id}$`));
	await expect(page.getByRole('heading', { name: collection.name, level: 1 })).toBeVisible();

	await openWithSlash(page);
	await input(page).fill(token);
	await row(page, new RegExp(`${type.label}.*Item type`)).click();
	await expect(page).toHaveURL(new RegExp(`/items\\?type=${type.slug}`));
	await expect(page.getByRole('link', { name: typed.name }).first()).toBeVisible();
	await expect(page.getByRole('link', { name: item.name })).toHaveCount(0);
});

test('searching Settings lists the Pages group and Enter goes there', async ({ page }) => {
	await openWithSlash(page);
	await input(page).fill('Settings');
	await expect(popup(page).getByText('Pages', { exact: true })).toBeVisible();
	const settings = popup(page).locator('[role="option"][data-value="page:/settings"]');
	await expect(settings).toBeVisible();
	await expect(settings).toHaveAttribute('aria-selected', 'true');
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(/\/settings$/);
});

test('a failing collections source keeps Items usable and recovers on retry', async ({
	page,
	request
}) => {
	const token = uniqueName('Failword');
	const item = await makeItem(request, `${token} item`);
	const collection = await makeCollection(request, `${token} set`);

	await openWithSlash(page);
	const unfail = await failCollectionSearch(page);
	await input(page).fill(token);

	const retry = popup(page).getByRole('button', { name: 'Try searching collections again' });
	await expect(popup(page).getByText("Couldn't search collections")).toBeVisible();
	await expect(retry).toBeVisible();
	await expect(row(page, new RegExp(item.name))).toBeVisible();
	await expect(row(page, new RegExp(item.name))).not.toHaveAttribute('aria-disabled', 'true');

	await unfail();
	await retry.click();
	await expect(row(page, new RegExp(collection.name))).toBeVisible();
	await expect(retry).toHaveCount(0);
});

test('Enter on Try again retries without opening another row', async ({ page, request }) => {
	const token = uniqueName('Keyword');
	await makeItem(request, `${token} item`);
	const collection = await makeCollection(request, `${token} set`);

	await openWithSlash(page);
	const unfail = await failCollectionSearch(page);
	await input(page).fill(token);
	const retry = popup(page).getByRole('button', { name: 'Try searching collections again' });
	await expect(retry).toBeVisible();

	await unfail();
	for (let i = 0; i < 6 && !(await retry.evaluate((el) => el === document.activeElement)); i++) {
		await page.keyboard.press('Tab');
	}
	await expect(retry).toBeFocused();
	await page.keyboard.press('Enter');

	await expect(row(page, new RegExp(collection.name))).toBeVisible();
	await expect(popup(page)).toBeVisible();
	await expect(page).toHaveURL(/\/$/);
});

test('a failed row is not actionable while the query is being retyped', async ({
	page,
	request
}) => {
	const token = uniqueName('Busyword');
	await makeCollection(request, `${token} set`);

	await openWithSlash(page);
	await failCollectionSearch(page);
	await input(page).fill(token);
	const retry = popup(page).getByRole('button', { name: 'Try searching collections again' });
	await expect(retry).toBeVisible();
	await expect(retry).toHaveAttribute('aria-disabled', 'false');

	await input(page).pressSequentially('x');
	await expect(retry).toHaveAttribute('aria-disabled', 'true');
	await expect(popup(page)).toBeVisible();
	await expect(page).toHaveURL(/\/$/);
});

test('Enter right after refining the query falls through to See all', async ({ page, request }) => {
	const token = uniqueName('Refineword');
	const item = await makeItem(request, `${token} item`);

	await openWithSlash(page);
	await input(page).fill(item.name);
	await expect(row(page, new RegExp(item.name))).toBeVisible();

	// The rows still on screen belong to the old query, so Enter must not open one.
	await input(page).pressSequentially('z');
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(/\/items/);
	await expect(page.getByPlaceholder('Search your items…')).toHaveValue(`${item.name}z`);
});

// Accent-insensitive matching, in both directions.

test('the popup finds accented and unaccented items whichever way you type', async ({
	page,
	request
}) => {
	const token = uniqueName('Accentword');
	const accented = await makeItem(request, `Café ${token}`);
	const plain = await makeItem(request, `Naive ${token}`);

	await openWithSlash(page);
	await input(page).fill(`cafe ${token}`);
	await expect(row(page, new RegExp(`^Café ${token}`))).toBeVisible();

	await input(page).fill(`Naïve ${token}`);
	await expect(row(page, new RegExp(`^Naive ${token}`))).toBeVisible();
	await row(page, new RegExp(`^Naive ${token}`)).click();
	await expect(page).toHaveURL(new RegExp(`/items/${plain.id}$`));
	expect(accented.id).not.toBe(plain.id);
});

test('the popup finds an accented collection with unaccented text', async ({ page, request }) => {
	const token = uniqueName('Accentset');
	const collection = await makeCollection(request, `Crème ${token}`);

	await openWithSlash(page);
	await input(page).fill(`creme ${token}`);
	const found = row(page, new RegExp(`^Crème ${token}`));
	await expect(found).toBeVisible();
	await expect(popup(page).getByText('Collections', { exact: true })).toBeVisible();
	await found.click();
	await expect(page).toHaveURL(new RegExp(`/collections/${collection.id}$`));
});

test('the items page box also finds an accented item with unaccented text', async ({
	page,
	request
}) => {
	const token = uniqueName('Accentlist');
	const item = await makeItem(request, `Café ${token}`);

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill(`cafe ${token}`);
	await expect(page.getByRole('link', { name: item.name }).first()).toBeVisible();
});

test('the status region says Searching… then one final count, never a partial one', async ({
	page,
	request
}) => {
	const token = uniqueName('Livewords');
	await makeItem(request, `${token} item`);
	await makeCollection(request, `${token} set`);
	await makeItemType(request, `${token} kind`);

	await openWithSlash(page);
	const status = popup(page).getByRole('status');
	await expect(status).toHaveText('');
	// Record every distinct text the region shows from here on.
	await status.evaluate((el) => {
		const seen: string[] = [];
		(window as unknown as { __statuses: string[] }).__statuses = seen;
		new MutationObserver(() => {
			const text = (el.textContent ?? '').trim();
			if (text && seen.at(-1) !== text) seen.push(text);
		}).observe(el, { childList: true, characterData: true, subtree: true });
	});

	await input(page).fill(token);
	await expect(status).toHaveText(/^\d+ results?$/);

	const seen = await page.evaluate(
		() => (window as unknown as { __statuses: string[] }).__statuses
	);
	// Any intermediate text is the spinner message; exactly one count, and it is the last.
	expect(seen.at(-1)).toMatch(/^\d+ results?$/);
	expect(seen.slice(0, -1).every((text) => text === 'Searching…')).toBe(true);
});
