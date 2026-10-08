import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { uniqueName } from './helpers';

/**
 * Collections: create, fill from both sides, search, remove with undo, rename and delete.
 * The database is shared, so each test only asserts on data it created and removes it through
 * the API afterwards.
 */
test.describe.configure({ mode: 'serial' });

// Ids of collections and items this spec created, deleted again in cleanup.
let ownCollectionIds: string[] = [];
let ownItemIds: string[] = [];

async function cleanUp(request: APIRequestContext) {
	for (const id of ownCollectionIds) await request.delete(`/api/v1/collection/${id}`);
	for (const id of ownItemIds) await request.delete(`/api/v1/node/${id}`);
	ownCollectionIds = [];
	ownItemIds = [];
}

test.afterEach(({ request }) => cleanUp(request));

/** Tracks the collection whose page the browser is on and returns its id. */
function trackCollectionFromUrl(page: Page): string {
	const id = new URL(page.url()).pathname.split('/').pop()!;
	ownCollectionIds.push(id);
	return id;
}

async function makeCollection(request: APIRequestContext, name: string, description?: string) {
	const res = await request.post('/api/v1/collection', { data: { name, description } });
	expect(res.status()).toBe(201);
	const created = (await res.json()) as { id: string; name: string };
	ownCollectionIds.push(created.id);
	return created;
}

async function makeItem(request: APIRequestContext, name: string) {
	const res = await request.post('/api/v1/node', { data: { name } });
	expect(res.status()).toBe(201);
	const created = (await res.json()) as { id: string; name: string };
	ownItemIds.push(created.id);
	return created;
}

async function addToCollection(request: APIRequestContext, collectionId: string, ids: string[]) {
	const res = await request.put(`/api/v1/collection/${collectionId}/item`, {
		data: { item_ids: ids }
	});
	expect(res.ok()).toBeTruthy();
}

async function expectNoShelfCopy(page: Page) {
	await expect(page.locator('body')).not.toContainText(/shelf|shelves|Not items/i);
}

// Vite compiles each route on first visit, which can outlast the default expect timeout.
test('warms up the routes', async ({ page, request }) => {
	test.setTimeout(120_000);
	const collection = await makeCollection(request, uniqueName('Warm'));
	const item = await makeItem(request, uniqueName('Warm item'));
	for (const path of [
		'/collections',
		`/collections/${collection.id}`,
		`/items/${item.id}`,
		'/items'
	]) {
		await page.goto(path, { waitUntil: 'networkidle' });
	}
});

test('creates a collection from the Collections page and lists it with No items', async ({
	page
}) => {
	const name = uniqueName('Vinyl');

	await page.goto('/collections');
	await expect(page.getByRole('heading', { name: 'Collections', level: 1 })).toBeVisible();
	await page.getByRole('button', { name: 'New collection' }).first().click();
	const dialog = page.getByRole('dialog', { name: 'New collection' });
	await dialog.getByLabel('Name').fill(name);
	await dialog.getByRole('button', { name: /^Create/ }).click();

	// Creating lands on the new collection's page.
	await page.waitForURL(/\/collections\/(?!$)[^/]+$/);
	trackCollectionFromUrl(page);
	await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
	await expect(page.getByText('No items', { exact: true })).toBeVisible();

	await page.goto('/collections');
	const card = page.getByRole('link', { name: new RegExp(name) });
	await expect(card).toBeVisible();
	await expect(card).toContainText('No items');
	await expectNoShelfCopy(page);
});

test('adds an item from the item page and shows it on the collection page', async ({
	page,
	request
}) => {
	const collection = await makeCollection(request, uniqueName('Films'));
	const item = await makeItem(request, uniqueName('Alien'));

	await page.goto(`/items/${item.id}`);
	const card = page.locator('[data-slot="card"]').filter({ hasText: 'Not in any collection yet.' });
	await expect(card).toBeVisible({ timeout: 20_000 });
	await card.getByRole('button', { name: 'Add to collection' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add to collection' });
	await dialog.getByRole('button', { name: collection.name }).click();
	await expect(page.getByText(`Added to ${collection.name}`)).toBeVisible();
	await expect(page.getByRole('link', { name: collection.name })).toBeVisible();

	await page.goto(`/collections/${collection.id}`);
	await expect(page.getByRole('heading', { name: collection.name, level: 1 })).toBeVisible();
	await expect(page.getByRole('link', { name: item.name }).first()).toBeVisible();
	await expect(page.getByText('1 item', { exact: true })).toBeVisible();
	await expectNoShelfCopy(page);
});

test('creates and adds from the item page', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Funko'));
	const name = uniqueName('Pops');

	await page.goto(`/items/${item.id}`);
	await page.getByRole('button', { name: 'Add to collection' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add to collection' });
	await dialog.getByLabel('New collection').fill(name);
	await dialog.getByRole('button', { name: 'Create and add' }).click();
	await expect(page.getByText(`Added to ${name}`)).toBeVisible();
	const link = page.getByRole('link', { name, exact: true });
	await expect(link).toBeVisible();
	ownCollectionIds.push((await link.getAttribute('href'))!.split('/').pop()!);
});

test('adds items from the collection page and marks ones already added', async ({
	page,
	request
}) => {
	const collection = await makeCollection(request, uniqueName('Picks'));
	const first = await makeItem(request, uniqueName('Pick A'));
	const second = await makeItem(request, uniqueName('Pick B'));
	await addToCollection(request, collection.id, [first.id]);

	await page.goto(`/collections/${collection.id}`);
	await page.getByRole('button', { name: 'Add items' }).first().click();
	const dialog = page.getByRole('dialog', { name: 'Add items' });
	await dialog.getByLabel('Search your items').fill('Pick ');

	const added = dialog.getByRole('checkbox', { name: `${first.name} (already added)` });
	await expect(added).toBeDisabled();
	await expect(added).toBeChecked();
	await expect(dialog.getByText('Already added')).toHaveCount(1);

	await dialog.getByRole('checkbox', { name: `Select ${second.name}` }).check();
	await dialog.getByRole('button', { name: 'Add 1 item' }).click();

	await expect(page.getByRole('link', { name: second.name }).first()).toBeVisible();
	await expect(page.getByText('2 items', { exact: true })).toBeVisible();
});

test('searches inside a collection', async ({ page, request }) => {
	const collection = await makeCollection(request, uniqueName('Search'));
	const apple = await makeItem(request, uniqueName('Apple'));
	const pear = await makeItem(request, uniqueName('Pear'));
	await addToCollection(request, collection.id, [apple.id, pear.id]);

	await page.goto(`/collections/${collection.id}`);
	await expect(page.getByRole('link', { name: apple.name }).first()).toBeVisible();
	await expect(page.getByRole('link', { name: pear.name }).first()).toBeVisible();

	await page.getByLabel('Search this collection').fill(apple.name);
	await expect(page.getByRole('link', { name: apple.name }).first()).toBeVisible();
	await expect(page.getByRole('link', { name: pear.name })).toHaveCount(0);

	await page.getByLabel('Search this collection').fill('zzz-no-match-zzz');
	await expect(page.getByText('Nothing matched "zzz-no-match-zzz"')).toBeVisible();
});

test('removes an item from a collection, keeps the item, and undo puts it back', async ({
	page,
	request
}) => {
	const collection = await makeCollection(request, uniqueName('Remove'));
	const item = await makeItem(request, uniqueName('Keeper'));
	await addToCollection(request, collection.id, [item.id]);

	await page.goto(`/collections/${collection.id}`);
	await expect(page.getByText('1 item', { exact: true })).toBeVisible();
	await page.getByRole('button', { name: `Remove ${item.name} from this collection` }).click();
	await expect(page.getByText(`Removed from ${collection.name}`)).toBeVisible();
	await expect(page.getByText('Nothing in this collection yet.')).toBeVisible();
	await expect(page.getByRole('button', { name: 'Add items' }).first()).toBeVisible();

	await page.getByRole('button', { name: 'Undo' }).click();
	await expect(page.getByRole('link', { name: item.name }).first()).toBeVisible();
	await expect(page.getByText('1 item', { exact: true })).toBeVisible();

	await page.getByRole('button', { name: `Remove ${item.name} from this collection` }).click();
	await expect(page.getByText('Nothing in this collection yet.')).toBeVisible();
	await page.goto(`/items/${item.id}`);
	await expect(page.getByText(item.name, { exact: true }).first()).toBeVisible();
});

test('renames a collection from the edit dialog', async ({ page, request }) => {
	const collection = await makeCollection(request, uniqueName('Old name'));
	const renamed = uniqueName('New name');

	await page.goto(`/collections/${collection.id}`);
	await page.getByRole('button', { name: 'Edit', exact: true }).click();
	const dialog = page.getByRole('dialog', { name: 'Edit collection' });
	await dialog.getByLabel('Name').fill(renamed);
	await dialog.getByRole('button', { name: 'Save' }).click();

	await expect(page.getByText('Collection saved')).toBeVisible();
	await expect(page.getByRole('heading', { name: renamed, level: 1 })).toBeVisible();
});

test('deletes a collection, keeps its items, and allows reusing the name', async ({
	page,
	request
}) => {
	const name = uniqueName('Doomed');
	const collection = await makeCollection(request, name);
	const item = await makeItem(request, uniqueName('Survivor'));
	await addToCollection(request, collection.id, [item.id]);

	await page.goto(`/collections/${collection.id}`);
	await page.getByRole('button', { name: 'Delete', exact: true }).click();
	await page
		.getByRole('dialog', { name: 'Delete this collection?' })
		.getByRole('button', { name: 'Delete', exact: true })
		.click();
	await expect(page.getByText('Collection deleted')).toBeVisible();
	await page.waitForURL(/\/collections$/);
	await expect(page.getByRole('link', { name: new RegExp(name) })).toHaveCount(0);

	const item2 = await request.get(`/api/v1/node/${item.id}`);
	expect(item2.ok()).toBeTruthy();

	await page.getByRole('button', { name: 'New collection' }).first().click();
	const dialog = page.getByRole('dialog', { name: 'New collection' });
	await dialog.getByLabel('Name').fill(name);
	await dialog.getByRole('button', { name: /^Create/ }).click();
	await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();

	await page.waitForURL(/\/collections\/(?!$)[^/]+$/);
	const freshId = trackCollectionFromUrl(page);
	expect(freshId).not.toBe(collection.id);
});

test('deleting an item drops the collection count', async ({ page, request }) => {
	const collection = await makeCollection(request, uniqueName('Shrinking'));
	const a = await makeItem(request, uniqueName('Gone'));
	const b = await makeItem(request, uniqueName('Stays'));
	await addToCollection(request, collection.id, [a.id, b.id]);

	await page.goto(`/collections/${collection.id}`);
	await expect(page.getByText('2 items', { exact: true })).toBeVisible();

	await page.goto(`/items/${a.id}`);
	await page.getByRole('button', { name: 'Edit', exact: true }).click();
	await page.getByRole('button', { name: 'Delete', exact: true }).click();
	await page
		.getByRole('dialog', { name: 'Delete item?' })
		.getByRole('button', { name: 'Delete', exact: true })
		.click();
	await page.waitForURL(/\/items$/);

	await page.goto('/collections');
	await expect(page.getByRole('link', { name: new RegExp(collection.name) })).toContainText(
		'1 item'
	);
});

// The collection ETag covers item_count, so revalidating after an item was deleted elsewhere
// returns the lower count.
test('the collection page count drops after an item is deleted', async ({ page, request }) => {
	const collection = await makeCollection(request, uniqueName('Shrinking page'));
	const a = await makeItem(request, uniqueName('Gone'));
	const b = await makeItem(request, uniqueName('Stays'));
	await addToCollection(request, collection.id, [a.id, b.id]);

	await page.goto(`/collections/${collection.id}`);
	await expect(page.getByText('2 items', { exact: true })).toBeVisible();
	await request.delete(`/api/v1/node/${a.id}`);

	await page.goto(`/collections/${collection.id}`);
	await expect(page.getByText('1 item', { exact: true })).toBeVisible();
});

const removeButtons = (page: Page) => page.locator('[data-remove-id]');
const removeButton = (page: Page, name: string) =>
	page.getByRole('button', { name: `Remove ${name} from this collection` });

test('removing a middle item keeps the others, moves focus to the next remove button', async ({
	page,
	request
}) => {
	const collection = await makeCollection(request, uniqueName('Focus'));
	const items = [
		await makeItem(request, uniqueName('Focus A')),
		await makeItem(request, uniqueName('Focus B')),
		await makeItem(request, uniqueName('Focus C'))
	];
	await addToCollection(
		request,
		collection.id,
		items.map((i) => i.id)
	);

	await page.goto(`/collections/${collection.id}`);
	await expect(removeButtons(page)).toHaveCount(3);
	const order = await removeButtons(page).evaluateAll((els) =>
		els.map((e) => e.getAttribute('data-remove-id'))
	);
	const [first, middle, last] = order as string[];
	const nameOf = (id: string) => items.find((i) => i.id === id)!.name;

	await removeButton(page, nameOf(middle)).click();
	await expect(page.getByText(`Removed from ${collection.name}`)).toBeVisible();
	await expect(removeButtons(page)).toHaveCount(2);
	await expect(page.locator(`[data-remove-id="${first}"]`)).toBeVisible();
	await expect(page.locator(`[data-remove-id="${last}"]`)).toBeVisible();
	await expect(page.locator(`[data-remove-id="${middle}"]`)).toHaveCount(0);
	await expect(page.locator(`[data-remove-id="${last}"]`)).toBeFocused();

	// Removing the last one falls back to the previous item.
	await removeButton(page, nameOf(last)).click();
	await expect(removeButtons(page)).toHaveCount(1);
	await expect(page.locator(`[data-remove-id="${first}"]`)).toBeFocused();

	// Removing the only one falls back to the header Add items button.
	await removeButton(page, nameOf(first)).click();
	await expect(page.getByText('Nothing in this collection yet.')).toBeVisible();
	await expect(page.getByRole('button', { name: 'Add items' }).first()).toBeFocused();
});

test('double-clicking Remove sends one request and Undo restores the item', async ({
	page,
	request
}) => {
	const collection = await makeCollection(request, uniqueName('Double'));
	const item = await makeItem(request, uniqueName('Double item'));
	await addToCollection(request, collection.id, [item.id]);

	let deletes = 0;
	page.on('request', (r) => {
		if (r.method() === 'DELETE' && r.url().includes(`/collection/${collection.id}/item/`)) {
			deletes += 1;
		}
	});

	await page.goto(`/collections/${collection.id}`);
	await expect(page.getByText('1 item', { exact: true })).toBeVisible();
	await removeButton(page, item.name).dblclick({ force: true });
	await expect(page.getByText('Nothing in this collection yet.')).toBeVisible();
	await expect(page.getByText('No items', { exact: true })).toBeVisible();
	expect(deletes).toBe(1);

	await page.getByRole('button', { name: 'Undo' }).click();
	await expect(removeButton(page, item.name)).toBeVisible();
	await expect(page.getByText('1 item', { exact: true })).toBeVisible();
});

test('clears and edits a collection description', async ({ page, request }) => {
	const description = uniqueName('About');
	const collection = await makeCollection(request, uniqueName('Described'), description);

	await page.goto(`/collections/${collection.id}`);
	await expect(page.getByText(description, { exact: true })).toBeVisible();

	// A non-empty edit still works.
	const edited = uniqueName('Edited about');
	await page.getByRole('button', { name: 'Edit', exact: true }).click();
	let dialog = page.getByRole('dialog', { name: 'Edit collection' });
	await dialog.getByLabel('Description').fill(edited);
	await dialog.getByRole('button', { name: 'Save' }).click();
	await expect(page.getByText('Collection saved')).toBeVisible();
	await expect(page.getByText(edited, { exact: true })).toBeVisible();
	await expect(page.getByText(description, { exact: true })).toHaveCount(0);

	// Emptying it removes the description, including after a reload.
	await page.getByRole('button', { name: 'Edit', exact: true }).click();
	dialog = page.getByRole('dialog', { name: 'Edit collection' });
	await dialog.getByLabel('Description').fill('');
	await dialog.getByRole('button', { name: 'Save' }).click();
	await expect(dialog).toBeHidden();
	await expect(page.getByText(edited, { exact: true })).toHaveCount(0);

	await page.reload();
	await expect(page.getByRole('heading', { name: collection.name, level: 1 })).toBeVisible();
	await expect(page.getByText(edited, { exact: true })).toHaveCount(0);
	await expect(page.getByText(description, { exact: true })).toHaveCount(0);
});

test('adding an unknown item id reports unknown or deleted items', async ({ request }) => {
	const collection = await makeCollection(request, uniqueName('Unknown'));
	const res = await request.put(`/api/v1/collection/${collection.id}/item`, {
		data: { item_ids: ['00000000-0000-7000-8000-000000000000'] }
	});
	expect(res.status()).toBe(400);
	expect(JSON.stringify(await res.json())).toContain('Unknown or deleted items');
});

test('an empty collection shows the empty state with an Add items button', async ({
	page,
	request
}) => {
	const collection = await makeCollection(request, uniqueName('Empty'));
	await page.goto(`/collections/${collection.id}`);
	await expect(page.getByText('Nothing in this collection yet.')).toBeVisible();
	await expect(page.getByRole('button', { name: 'Add items' })).toHaveCount(2);
	await page.getByRole('button', { name: 'Add items' }).last().click();
	await expect(page.getByRole('dialog', { name: 'Add items' })).toBeVisible();
	await expectNoShelfCopy(page);
});

test('the Collections navigation entry opens /collections', async ({ page }) => {
	await page.goto('/');
	await page.getByRole('link', { name: 'Collections' }).first().click();
	await page.waitForURL(/\/collections$/);
	await expect(page.getByRole('heading', { name: 'Collections', level: 1 })).toBeVisible();
});
