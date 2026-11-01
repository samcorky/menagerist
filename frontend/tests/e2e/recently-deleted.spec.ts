import { test, expect, type APIRequestContext, type Page } from './fixtures';
import { asUser, createUserViaApi, ownedData, uniqueName } from './helpers';

/**
 * Recently deleted: items and collections are deleted through the API, then restored or purged
 * from the page. The database is shared, so every assertion is about rows this spec created.
 */
test.describe.configure({ mode: 'serial' });

const { makeCollection, makeItem, addToCollection, cleanUp } = ownedData();
const edgeTypeIds: string[] = [];

test.afterEach(async ({ request }) => {
	await cleanUp(request);
	for (const id of edgeTypeIds.splice(0)) await request.delete(`/api/v1/edge-type/${id}`);
});

async function makeEdgeType(request: APIRequestContext, suffix: string) {
	const slug = `deleted-link-${suffix}`.toLowerCase().replace(/[^a-z0-9]+/g, '-');
	const label = `Linked to ${suffix}`;
	const res = await request.post('/api/v1/edge-type', {
		data: { slug, label, reverse_label: `Linked from ${suffix}`, directional: true }
	});
	expect(res.status(), await res.text()).toBe(201);
	edgeTypeIds.push(((await res.json()) as { id: string }).id);
	return { slug, label };
}

async function openRecentlyDeleted(page: Page, tab: 'Items' | 'Collections') {
	await page.goto('/recently-deleted');
	await expect(page.getByRole('heading', { name: 'Recently deleted' })).toBeVisible();
	await page.getByRole('button', { name: new RegExp(`^${tab}`) }).click();
}

const row = (page: Page, name: string) =>
	page.getByRole('row').filter({ has: page.getByText(name, { exact: true }) });

test('restores a deleted item with its connection', async ({ page, request }) => {
	const suffix = uniqueName('r');
	const edgeType = await makeEdgeType(request, suffix);
	const item = await makeItem(request, `Deleted restore ${suffix}`);
	const other = await makeItem(request, `Deleted partner ${suffix}`);
	const edge = await request.post('/api/v1/edge', {
		data: { source_id: item.id, target_id: other.id, type: edgeType.slug }
	});
	expect(edge.status(), await edge.text()).toBe(201);
	expect((await request.delete(`/api/v1/node/${item.id}`)).status()).toBe(204);

	await openRecentlyDeleted(page, 'Items');
	const deleted = row(page, item.name);
	await expect(deleted).toContainText('Deleted just now');
	await deleted.getByRole('button', { name: `Restore ${item.name}` }).click();
	await expect(deleted).toHaveCount(0);

	await page.goto(`/items/${item.id}`);
	await expect(page.getByText(item.name, { exact: true }).first()).toBeVisible();
	await expect(page.getByRole('link', { name: other.name })).toBeVisible();
});

test('purges a deleted item for good', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Deleted purge'));
	expect((await request.delete(`/api/v1/node/${item.id}`)).status()).toBe(204);

	await openRecentlyDeleted(page, 'Items');
	await row(page, item.name)
		.getByRole('button', { name: `Purge ${item.name}` })
		.click();
	const dialog = page.getByRole('dialog');
	await expect(dialog).toContainText(
		`This permanently deletes ${item.name}. This cannot be undone.`
	);
	await dialog.getByRole('button', { name: 'Purge', exact: true }).click();
	await expect(row(page, item.name)).toHaveCount(0);

	expect((await request.get(`/api/v1/node/${item.id}`)).status()).toBe(404);
	await openRecentlyDeleted(page, 'Items');
	await expect(page.getByRole('heading', { name: 'Recently deleted' })).toBeVisible();
	await expect(row(page, item.name)).toHaveCount(0);
});

test('restores and purges collections', async ({ page, request }) => {
	const kept = await makeCollection(request, uniqueName('Deleted keep'));
	const gone = await makeCollection(request, uniqueName('Deleted gone'));
	const member = await makeItem(request, uniqueName('Deleted member'));
	await addToCollection(request, kept.id, [member.id]);
	expect((await request.delete(`/api/v1/collection/${kept.id}`)).status()).toBe(204);
	expect((await request.delete(`/api/v1/collection/${gone.id}`)).status()).toBe(204);

	await openRecentlyDeleted(page, 'Collections');
	await expect(row(page, kept.name)).toContainText('List');
	await row(page, kept.name)
		.getByRole('button', { name: `Restore ${kept.name}` })
		.click();
	await expect(row(page, kept.name)).toHaveCount(0);
	await page.goto(`/collections/${kept.id}`);
	await expect(page.getByRole('heading', { name: kept.name })).toBeVisible();
	await expect(page.getByText(member.name, { exact: true }).first()).toBeVisible();

	await openRecentlyDeleted(page, 'Collections');
	await row(page, gone.name)
		.getByRole('button', { name: `Purge ${gone.name}` })
		.click();
	await page.getByRole('dialog').getByRole('button', { name: 'Purge', exact: true }).click();
	await expect(row(page, gone.name)).toHaveCount(0);
	expect((await request.get(`/api/v1/collection/${gone.id}`)).status()).toBe(404);
	await openRecentlyDeleted(page, 'Collections');
	await expect(page.getByRole('heading', { name: 'Recently deleted' })).toBeVisible();
	await expect(row(page, gone.name)).toHaveCount(0);
});

test('another account sees nothing of it', async ({ browser, request, workerBaseURL }) => {
	const item = await makeItem(request, uniqueName('Deleted private'));
	const collection = await makeCollection(request, uniqueName('Deleted private list'));
	await request.delete(`/api/v1/node/${item.id}`);
	await request.delete(`/api/v1/collection/${collection.id}`);

	const user = await createUserViaApi(request, workerBaseURL, { prefix: 'deleted-b' });
	const other = await asUser(browser, user);
	try {
		await openRecentlyDeleted(other.page, 'Items');
		await expect(other.page.getByText('Nothing has been deleted.')).toBeVisible();
		await expect(other.page.getByText(item.name)).toHaveCount(0);
		await openRecentlyDeleted(other.page, 'Collections');
		await expect(other.page.getByText('Nothing has been deleted.')).toBeVisible();
		await expect(other.page.getByText(collection.name)).toHaveCount(0);
		expect((await other.request.post(`/api/v1/node/${item.id}/restore`)).status()).toBe(404);
		expect((await other.request.delete(`/api/v1/node/${item.id}/purge`)).status()).toBe(404);
	} finally {
		await other.context.close();
	}
});
