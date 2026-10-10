import { test, expect } from './fixtures';
import { createItem, createItemType, uniqueName } from './helpers';
import { MOVIES, MUSIC, exampleData, install, openItem, remove } from './examples-helpers';

/**
 * Example packs: removing a pack, what removal keeps and why, and reinstalling. Serial, and every test cleans up through the API afterwards.
 */
test.describe.configure({ mode: 'serial' });

const { ownNames, ownTypeLabels, cleanUp } = exampleData();

test.beforeEach(({ request }) => cleanUp(request));
test.afterEach(({ request }) => cleanUp(request));

test('removing a pack removes its items and item types', async ({ page }) => {
	await install(page, MUSIC);
	const ownType = uniqueName('Plain Type');
	ownTypeLabels.push(ownType);
	await createItemType(page, { label: ownType });

	await page.goto('/settings/item-types');
	const typeCard = (text: string) =>
		page.locator('[data-slot="card"]').filter({ has: page.getByText(text, { exact: true }) });
	const exampleCard = typeCard('music-record');
	await expect(exampleCard).toBeVisible();
	await expect(exampleCard.getByText('Example', { exact: true })).toBeVisible();
	await expect(typeCard(ownType)).toBeVisible();
	await expect(typeCard(ownType).getByText('Example', { exact: true })).toHaveCount(0);

	await remove(page, MUSIC);
	await expect(page.getByText(/^Removed /)).toBeVisible();
	await expect(page.getByRole('button', { name: /^Add Music/ })).toBeVisible();

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill('Night Drive');
	await expect(page.getByRole('link', { name: 'Night Drive' })).toHaveCount(0);
	await expect(page.getByLabel('Examples', { exact: true })).toHaveCount(0);
	await expect(page.getByText('Example', { exact: true })).toHaveCount(0);

	await page.goto('/settings/item-types');
	await expect(page.getByRole('heading', { name: 'Item types' })).toBeVisible();
	await expect(page.getByText('music-record', { exact: true })).toHaveCount(0);
	await expect(page.getByText(/^music-/)).toHaveCount(0);
	await expect(typeCard(ownType)).toBeVisible();
	await expect(page.getByText('Example', { exact: true })).toHaveCount(0);
});

test('keeps an edited example item on removal and says why', async ({ page }) => {
	await install(page, MUSIC);
	await openItem(page, 'Paper Lanterns');

	const edited = uniqueName('Edited Lanterns');
	ownNames.push(edited);
	await page.getByRole('button', { name: 'Edit', exact: true }).click();
	await page.getByLabel('Name').fill(edited);
	await page.getByRole('button', { name: 'Save changes' }).click();
	await expect(page.getByText(edited, { exact: true }).first()).toBeVisible();

	await remove(page, MUSIC);
	await expect(page.getByRole('region', { name: /Notifications/ })).toContainText(
		'kept because you edited them'
	);
	await expect(page.getByText('item was kept because you edited them.')).toBeVisible();

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill(edited);
	const keptCard = page.getByRole('link', { name: edited }).first();
	await expect(keptCard).toBeVisible();
	await expect(keptCard.getByText('Example', { exact: true })).toHaveCount(0);
	await expect(page.getByLabel('Examples', { exact: true })).toHaveCount(0);

	await keptCard.click();
	await expect(page.getByText(edited, { exact: true }).first()).toBeVisible();
	await expect(page.getByText('Example', { exact: true })).toHaveCount(0);
});

test('keeps an example item that has your own connection', async ({ page }) => {
	await install(page, MOVIES);
	const own = uniqueName('My own item');
	ownNames.push(own);
	await createItem(page, { name: own });

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill('');
	const firstExample = await page.request
		.get('/api/v1/node?limit=500')
		.then((r) => r.json() as Promise<{ id: string; name: string; type: string | null }[]>)
		.then((nodes) => nodes.find((n) => n.type?.startsWith('movies-')));
	expect(firstExample).toBeTruthy();
	ownNames.push(firstExample!.name);

	await page.goto(`/items/${firstExample!.id}`);
	await expect(page.getByText(firstExample!.name, { exact: true }).first()).toBeVisible();
	// Example items already have connections, so scope the label to the form's own input.
	await page.getByRole('textbox', { name: 'Connection', exact: true }).fill('related-to');
	const targetSearch = page.getByPlaceholder('Search items…');
	await targetSearch.fill(own);
	await page
		.getByRole('button', { name: new RegExp(own) })
		.first()
		.click();
	await targetSearch.blur();
	await page.waitForTimeout(250);
	await page.getByRole('button', { name: /^Connect items?$/ }).click();
	await expect(page.getByRole('link', { name: own })).toBeVisible();

	await remove(page, MOVIES);
	await expect(
		page.getByText('item was kept because they have your connections, files or collections.')
	).toBeVisible();

	await page.goto(`/items/${firstExample!.id}`);
	await expect(page.getByText(firstExample!.name, { exact: true }).first()).toBeVisible();
});

test('reinstalls a pack after removing it', async ({ page }) => {
	await install(page, MUSIC);
	await remove(page, MUSIC);
	await expect(page.getByRole('button', { name: /^Add Music/ })).toBeVisible();

	await install(page, MUSIC);
	await openItem(page, 'Night Drive');
});
