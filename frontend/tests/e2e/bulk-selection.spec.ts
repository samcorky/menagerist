import { test, expect, type Page, type APIRequestContext } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * Bulk selection (#499): pick items on the Items list or a collection page and act on them in
 * one request. The database is shared, so each test searches for the unique prefix it made.
 */
test.describe.configure({ mode: 'serial' });

const { makeCollection, makeItem, addToCollection, cleanUp } = ownedData();
const edgeTypeIds: string[] = [];

test.afterEach(async ({ request }) => {
	await cleanUp(request);
	for (const id of edgeTypeIds.splice(0)) await request.delete(`/api/v1/edge-types/${id}`);
});

// Vite compiles each route on first visit, which can outlast the default expect timeout.
test('warms up the routes', async ({ page, request }) => {
	test.setTimeout(120_000);
	const collection = await makeCollection(request, uniqueName('Warm'));
	for (const path of ['/items', `/collections/${collection.id}`]) {
		await page.goto(path, { waitUntil: 'networkidle' });
	}
});

async function makeItems(request: APIRequestContext, prefix: string, count: number) {
	const items = [];
	for (let i = 1; i <= count; i++) items.push(await makeItem(request, `${prefix} ${i}`));
	return items;
}

async function openItems(page: Page, prefix: string) {
	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill(prefix);
	await expect(page.getByRole('link', { name: new RegExp(`${prefix} 1`) })).toBeVisible();
}

const bar = (page: Page) => page.getByRole('toolbar', { name: 'Actions for selected items' });

test('Select shows checkboxes and a count, and Done changes nothing', async ({ page, request }) => {
	const prefix = uniqueName('Pick').replace(/\W+/g, '');
	await makeItems(request, prefix, 3);
	await openItems(page, prefix);

	await page.getByRole('button', { name: 'Select', exact: true }).click();
	await expect(bar(page).getByTestId('selection-count')).toHaveText('0 selected');
	await page.getByRole('checkbox', { name: `Select ${prefix} 1` }).click();
	await expect(bar(page).getByTestId('selection-count')).toHaveText('1 selected');

	await bar(page).getByRole('button', { name: 'Done' }).click();
	await expect(bar(page)).toHaveCount(0);
	await expect(page.getByRole('link', { name: new RegExp(`${prefix} 3`) })).toBeVisible();
});

test('Select all is three-state and covers the rows in view', async ({ page, request }) => {
	const prefix = uniqueName('All').replace(/\W+/g, '');
	await makeItems(request, prefix, 3);
	await openItems(page, prefix);
	await page.getByRole('button', { name: 'Select', exact: true }).click();
	const all = bar(page).getByRole('checkbox', { name: 'Select all' });

	await expect(all).toHaveAttribute('aria-checked', 'false');
	await page.getByRole('checkbox', { name: `Select ${prefix} 1` }).click();
	await expect(all).toHaveAttribute('aria-checked', 'mixed');
	await all.click();
	await expect(all).toHaveAttribute('aria-checked', 'true');
	await expect(bar(page).getByTestId('selection-count')).toHaveText('3 selected');
	await all.click();
	await expect(bar(page).getByTestId('selection-count')).toHaveText('0 selected');
});

test('the selection survives a new search and says how many are out of view', async ({
	page,
	request
}) => {
	const prefix = uniqueName('Keep').replace(/\W+/g, '');
	await makeItems(request, prefix, 3);
	await openItems(page, prefix);
	await page.getByRole('button', { name: 'Select', exact: true }).click();
	await page.getByRole('checkbox', { name: `Select ${prefix} 1` }).click();
	await page.getByRole('checkbox', { name: `Select ${prefix} 2` }).click();

	await page.getByPlaceholder('Search your items…').fill(`${prefix} 3`);
	await expect(page.getByRole('checkbox', { name: `Select ${prefix} 2` })).toHaveCount(0);
	await page.getByRole('checkbox', { name: `Select ${prefix} 3` }).click();

	await expect(bar(page).getByTestId('selection-count')).toHaveText('3 selected, 2 not in view');
});

test('delete shows Undo, Undo keeps the items, and letting it lapse removes them', async ({
	page,
	request
}) => {
	const prefix = uniqueName('Del').replace(/\W+/g, '');
	const items = await makeItems(request, prefix, 3);
	await openItems(page, prefix);
	await page.getByRole('button', { name: 'Select', exact: true }).click();
	await bar(page).getByRole('checkbox', { name: 'Select all' }).click();

	await bar(page).getByRole('button', { name: 'Delete' }).click();
	await expect(page.getByText('3 items deleted')).toBeVisible();
	await page.getByRole('button', { name: 'Undo' }).click();
	// Still selecting, so the rows are checkboxes rather than links, and Undo picks them again.
	await expect(page.getByRole('checkbox', { name: `Select ${prefix} 1` })).toBeVisible();
	await expect(bar(page).getByTestId('selection-count')).toHaveText('3 selected');
	expect((await request.get(`/api/v1/nodes/${items[0].id}`)).status()).toBe(200);
	// The first toast must be gone, or the second delete shows two with the same text.
	await expect(page.getByText('3 items deleted')).toHaveCount(0);

	await bar(page).getByRole('button', { name: 'Delete' }).click();
	await expect(page.getByText('3 items deleted')).toBeVisible();
	await expect
		.poll(async () => (await request.get(`/api/v1/nodes/${items[0].id}`)).status(), {
			timeout: 15_000
		})
		.toBe(404);
	for (const item of items.slice(1)) {
		expect((await request.get(`/api/v1/nodes/${item.id}`)).status()).toBe(404);
	}
});

test('searching while a delete waits does not send it, and Undo still works', async ({
	page,
	request
}) => {
	const prefix = uniqueName('Wait').replace(/\W+/g, '');
	const items = await makeItems(request, prefix, 3);
	await openItems(page, prefix);
	await page.getByRole('button', { name: 'Select', exact: true }).click();
	await bar(page).getByRole('checkbox', { name: 'Select all' }).click();
	await bar(page).getByRole('button', { name: 'Delete' }).click();
	await expect(page.getByText('3 items deleted')).toBeVisible();

	// A search rewrites the URL on the same page; it must not commit the delete.
	await page.getByPlaceholder('Search your items…').fill(`${prefix} 1`);
	await page.getByPlaceholder('Search your items…').fill(prefix);
	await expect(page.getByText('3 items deleted')).toBeVisible();
	expect((await request.get(`/api/v1/nodes/${items[0].id}`)).status()).toBe(200);

	await page.getByRole('button', { name: 'Undo' }).click();
	await expect(page.getByRole('checkbox', { name: `Select ${prefix} 1` })).toBeVisible();
	expect((await request.get(`/api/v1/nodes/${items[0].id}`)).status()).toBe(200);
});

test('tags every selected item', async ({ page, request }) => {
	const prefix = uniqueName('Tag').replace(/\W+/g, '');
	const items = await makeItems(request, prefix, 2);
	await openItems(page, prefix);
	await page.getByRole('button', { name: 'Select', exact: true }).click();
	await bar(page).getByRole('checkbox', { name: 'Select all' }).click();

	await bar(page).getByRole('button', { name: 'Tag' }).click();
	const dialog = page.getByRole('dialog', { name: 'Tag 2 items' });
	await dialog.getByLabel('Add tags').fill('bulk-one, Bulk-Two');
	await dialog.getByRole('button', { name: 'Apply' }).click();
	await expect(page.getByText('Tagged 2 items')).toBeVisible();

	for (const item of items) {
		const body = await (await request.get(`/api/v1/nodes/${item.id}`)).json();
		expect(body.tags).toEqual(['bulk-one', 'bulk-two']);
	}
});

test('adds the selected items to a collection', async ({ page, request }) => {
	const prefix = uniqueName('Add').replace(/\W+/g, '');
	const items = await makeItems(request, prefix, 3);
	const collection = await makeCollection(request, uniqueName('Shelf'));
	await openItems(page, prefix);
	await page.getByRole('button', { name: 'Select', exact: true }).click();
	await bar(page).getByRole('checkbox', { name: 'Select all' }).click();

	await bar(page).getByRole('button', { name: 'Add to collection' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add 3 items to a collection' });
	await dialog.getByLabel('Collection').selectOption(collection.id);
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(page.getByText('Added 3 items')).toBeVisible();

	const members = await (
		await request.get(`/api/v1/nodes?collection=${collection.id}&limit=50`)
	).json();
	expect(members.map((m: { id: string }) => m.id).sort()).toEqual(items.map((i) => i.id).sort());
});

test('removes the selected items from the collection being viewed', async ({ page, request }) => {
	const prefix = uniqueName('Rem').replace(/\W+/g, '');
	const items = await makeItems(request, prefix, 3);
	const collection = await makeCollection(request, uniqueName('Shelf'));
	await addToCollection(
		request,
		collection.id,
		items.map((i) => i.id)
	);
	await page.goto(`/collections/${collection.id}`);
	await expect(page.getByRole('link', { name: new RegExp(`${prefix} 1`) })).toBeVisible();

	await page.getByRole('button', { name: 'Select', exact: true }).click();
	await page.getByRole('checkbox', { name: `Select ${prefix} 1` }).click();
	await page.getByRole('checkbox', { name: `Select ${prefix} 2` }).click();
	await bar(page)
		.getByRole('button', { name: /^Remove from / })
		.click();

	await expect(page.getByText(/Removed 2 items from/)).toBeVisible();
	const members = await (
		await request.get(`/api/v1/nodes?collection=${collection.id}&limit=50`)
	).json();
	expect(members.map((m: { id: string }) => m.id)).toEqual([items[2].id]);
});

/** Writes screenshots when SHOTS_DIR is set (manual review and the pull request only). */
test('screenshots: list, grid and the tag dialog', async ({ page, request }) => {
	const dir = process.env.SHOTS_DIR;
	test.skip(!dir, 'screenshots only');
	await page.setViewportSize({ width: 1100, height: 800 });
	const prefix = uniqueName('Shot').replace(/\W+/g, '');
	await makeItems(request, prefix, 4);
	await openItems(page, prefix);
	await page.getByRole('button', { name: 'Select', exact: true }).click();
	await page.getByRole('checkbox', { name: `Select ${prefix} 1` }).click();
	await page.getByRole('checkbox', { name: `Select ${prefix} 2` }).click();
	await page.screenshot({ path: `${dir}/bulk-list.png` });

	await page.getByRole('button', { name: 'Grid view' }).click();
	await page.screenshot({ path: `${dir}/bulk-grid.png` });

	await bar(page).getByRole('button', { name: 'Tag' }).click();
	await page.getByRole('dialog').getByLabel('Add tags').fill('to-watch');
	await page.screenshot({ path: `${dir}/bulk-tag-dialog.png` });
});

test('connects several items to one through a connection type', async ({ page, request }) => {
	const prefix = uniqueName('Con').replace(/\W+/g, '');
	const items = await makeItems(request, prefix, 3);
	const box = await makeItem(request, `${prefix} Box`);
	const label = uniqueName('Kept in');
	const created = await request.post('/api/v1/edge-types', {
		data: {
			slug: label.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
			label,
			reverse_label: 'Keeps',
			directional: true
		}
	});
	expect(created.status(), await created.text()).toBe(201);
	const edgeType = (await created.json()) as { id: string; slug: string };
	edgeTypeIds.push(edgeType.id);

	await openItems(page, prefix);
	await page.getByRole('button', { name: 'Select', exact: true }).click();
	for (const item of items) {
		await page.getByRole('checkbox', { name: `Select ${item.name}` }).click();
	}
	await bar(page).getByRole('button', { name: 'Connect' }).click();
	const dialog = page.getByRole('dialog', { name: 'Connect 3 items to one item' });
	await dialog.getByLabel('Connection').selectOption(edgeType.slug);
	await dialog.getByLabel('To this item').fill(`${prefix} Box`);
	await dialog.getByRole('radio', { name: `Connect to ${box.name}` }).check();
	await dialog.getByRole('button', { name: 'Connect', exact: true }).click();
	await expect(page.getByText('Connected 3 items')).toBeVisible();

	const edges = await (await request.get(`/api/v1/edges?node_id=${box.id}&limit=50`)).json();
	expect(edges).toHaveLength(3);
	for (const edge of edges) {
		expect(edge.target_id).toBe(box.id);
		expect(items.map((i) => i.id)).toContain(edge.source_id);
	}
});
