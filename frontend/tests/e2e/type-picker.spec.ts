import { test, expect, type Page } from './fixtures';
import { chooseItemType, openQuickCapture, ownedData, uniqueName } from './helpers';

/** The item type picker: searchable, the types you use first, and create-as-you-type. */
const { makeItem, makeItemType, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const picker = (page: Page) => page.getByRole('combobox', { name: 'Item type' });

test('types you have items in come first, with their counts', async ({ page, request }) => {
	const used = await makeItemType(request, uniqueName('Used'));
	const unused = await makeItemType(request, uniqueName('Unused'));
	await makeItem(request, uniqueName('Thing'), used.slug);
	await makeItem(request, uniqueName('Thing'), used.slug);

	await page.goto('/items/new');
	await picker(page).click();
	const list = page.getByRole('listbox');
	await expect(list.getByText('In use', { exact: true })).toBeVisible();
	await expect(list.getByText('Other item types', { exact: true })).toBeVisible();
	const options = await list.getByRole('option').allInnerTexts();
	const usedAt = options.findIndex((text) => text.includes(used.label));
	const unusedAt = options.findIndex((text) => text.includes(unused.label));
	expect(usedAt).toBeGreaterThanOrEqual(0);
	expect(usedAt).toBeLessThan(unusedAt);
	await expect(list.getByRole('option', { name: new RegExp(used.label) })).toContainText('2');
});

test('searching narrows the list, and a new name offers to create it', async ({
	page,
	request
}) => {
	const film = await makeItemType(request, uniqueName('Filmish'));
	await page.goto('/items/new');
	await picker(page).click();
	await page.getByPlaceholder('Search item types…').fill(film.label.slice(0, 10));
	await expect(page.getByRole('option', { name: new RegExp(film.label) })).toBeVisible();

	const fresh = uniqueName('Brand new');
	await page.getByPlaceholder('Search item types…').fill(fresh);
	await expect(page.getByRole('option', { name: `Create “${fresh}”` })).toBeVisible();
	await page.getByPlaceholder('Search item types…').fill(film.label);
	await expect(page.getByRole('option', { name: /^Create/ })).toHaveCount(0);
});

test('creating a type from the new item form selects it and saves the item with it', async ({
	page
}) => {
	const typeLabel = uniqueName('Vinyl');
	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Kind of Blue'));
	await picker(page).click();
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('option', { name: `Create “${typeLabel}”` }).click();
	await expect(picker(page)).toContainText(typeLabel);

	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);
	await expect(page.getByText(typeLabel, { exact: true }).first()).toBeVisible();
});

test('choosing no type clears the choice', async ({ page, request }) => {
	const type = await makeItemType(request, uniqueName('Clearable'));
	await page.goto('/items/new');
	await chooseItemType(page, type.label);
	await expect(picker(page)).toContainText(type.label);

	await picker(page).click();
	await page.getByRole('option', { name: 'No item type' }).click();
	await expect(picker(page)).not.toContainText(type.label);
});

test('Quick capture creates a type inline, with no second form', async ({ page }) => {
	const typeLabel = uniqueName('Capture type');
	await page.goto('/');
	const dialog = await openQuickCapture(page);
	await dialog.getByPlaceholder('Name…').fill(uniqueName('Captured'));
	await dialog.getByRole('combobox', { name: 'Item type' }).click();
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('option', { name: `Create “${typeLabel}”` }).click();
	await expect(dialog.getByRole('combobox', { name: 'Item type' })).toContainText(typeLabel);
	await expect(dialog.getByText('+ New item type')).toHaveCount(0);
});

test('an item with no type is given one on its own page, by search or by creating', async ({
	page,
	request
}) => {
	const existing = await makeItemType(request, uniqueName('Existing'));
	const item = await makeItem(request, uniqueName('Untyped'));
	await page.goto(`/items/${item.id}`);
	await expect(page.getByText('No item type - pick or create one:')).toBeVisible();

	await chooseItemType(page, existing.label);
	await expect(page.getByText('No item type - pick or create one:')).toHaveCount(0);
	await expect(page.getByText(existing.label, { exact: true }).first()).toBeVisible();

	const other = await makeItem(request, uniqueName('Untyped two'));
	const created = uniqueName('Made here');
	await page.goto(`/items/${other.id}`);
	await picker(page).click();
	await page.getByPlaceholder('Search item types…').fill(created);
	await page.getByRole('option', { name: `Create “${created}”` }).click();
	await expect(page.getByText(created, { exact: true }).first()).toBeVisible();
	await expect(page.getByText('No item type - pick or create one:')).toHaveCount(0);
});
