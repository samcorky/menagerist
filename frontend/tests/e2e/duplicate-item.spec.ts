import { test, expect, type APIRequestContext, type Page } from './fixtures';
import { coverOf, mediaOf, setOwnCover } from './examples-helpers';
import { ownedData, uniqueName } from './helpers';

/** Duplicating an item makes a new item with its own history; extras are opt-in. */
const { makeItem, makeCollection, addToCollection, cleanUp } = ownedData();

let copyIds: string[] = [];

test.afterEach(async ({ request }) => {
	for (const id of copyIds) await request.delete(`/api/v1/nodes/${id}`);
	copyIds = [];
	await cleanUp(request);
});

/** Submits the open dialog and waits for the copy's page; returns the copy's id. */
async function submitAndOpenCopy(page: Page, name: string): Promise<string> {
	const from = new URL(page.url()).pathname;
	await page
		.getByRole('dialog', { name: 'Duplicate item' })
		.getByRole('button', { name: 'Duplicate' })
		.click();
	await page.waitForURL((url) => url.pathname !== from);
	await expect(page.getByText(name).first()).toBeVisible();
	const id = new URL(page.url()).pathname.split('/').pop()!;
	copyIds.push(id);
	return id;
}

async function duplicate(page: Page, name: string, untick: string[] = []) {
	await page.getByRole('button', { name: 'Duplicate' }).click();
	const dialog = page.getByRole('dialog', { name: 'Duplicate item' });
	await dialog.getByLabel('Name').fill(name);
	for (const label of untick) await dialog.getByLabel(label).uncheck();
	return submitAndOpenCopy(page, name);
}

const inCollection = async (request: APIRequestContext, collectionId: string) => {
	const res = await request.get(`/api/v1/nodes?collection=${collectionId}`);
	return ((await res.json()) as { id: string }[]).map((item) => item.id);
};

test('the dialog offers a copy name and starts with only collections ticked', async ({
	page,
	request
}) => {
	const item = await makeItem(request, uniqueName('Original'));

	await page.goto(`/items/${item.id}`);
	await page.getByRole('button', { name: 'Duplicate' }).click();

	const dialog = page.getByRole('dialog', { name: 'Duplicate item' });
	await expect(dialog.getByLabel('Name')).toHaveValue(`Copy of ${item.name}`);
	await expect(dialog.getByLabel('Connections')).not.toBeChecked();
	await expect(dialog.getByLabel('Photos and files')).not.toBeChecked();
	await expect(dialog.getByLabel('Cover image')).not.toBeChecked();
	await expect(dialog.getByLabel('Collections')).toBeChecked();
});

test('a copy keeps the details and joins the same collections', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Original'));
	const patch = await request.patch(`/api/v1/nodes/${item.id}`, {
		data: { description: 'Worth a second copy', tags: ['series'] }
	});
	expect(patch.ok()).toBeTruthy();
	const shelf = await makeCollection(request, uniqueName('Shelf'));
	await addToCollection(request, shelf.id, [item.id]);

	await page.goto(`/items/${item.id}`);
	const copyName = uniqueName('Variant');
	const copyId = await duplicate(page, copyName);

	expect(copyId).not.toBe(item.id);
	await expect(page.getByText('Worth a second copy')).toBeVisible();
	const copy = (await (await request.get(`/api/v1/nodes/${copyId}`)).json()) as {
		tags: string[];
	};
	expect(copy.tags).toEqual(['series']);
	expect(await inCollection(request, shelf.id)).toEqual(expect.arrayContaining([item.id, copyId]));
});

test('unticking collections leaves the copy off the shelf', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Original'));
	const shelf = await makeCollection(request, uniqueName('Shelf'));
	await addToCollection(request, shelf.id, [item.id]);

	await page.goto(`/items/${item.id}`);
	const copyId = await duplicate(page, uniqueName('Loner'), ['Collections']);

	expect(await inCollection(request, shelf.id)).toEqual([item.id]);
	expect(await inCollection(request, shelf.id)).not.toContain(copyId);
});

test('connections are copied only when ticked', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Original'));
	const other = await makeItem(request, uniqueName('Other'));
	const edge = await request.post('/api/v1/edges', {
		data: { source_id: item.id, target_id: other.id, type: 'related-to' }
	});
	expect(edge.status()).toBe(201);

	await page.goto(`/items/${item.id}`);
	const plain = await duplicate(page, uniqueName('Plain'));
	let edges = (await (await request.get(`/api/v1/edges?node_id=${plain}`)).json()) as unknown[];
	expect(edges).toHaveLength(0);

	await page.goto(`/items/${item.id}`);
	await page.getByRole('button', { name: 'Duplicate' }).click();
	const dialog = page.getByRole('dialog', { name: 'Duplicate item' });
	const linkedName = uniqueName('Linked');
	await dialog.getByLabel('Name').fill(linkedName);
	await dialog.getByLabel('Connections').check();
	const linked = await submitAndOpenCopy(page, linkedName);
	edges = (await (await request.get(`/api/v1/edges?node_id=${linked}`)).json()) as unknown[];
	expect(edges).toHaveLength(1);
});

test('a copied cover is its own file: deleting it leaves the original', async ({
	page,
	request
}) => {
	const item = await makeItem(request, uniqueName('Original'));
	await setOwnCover(request, item.id);
	const original = await coverOf(request, item.id);
	expect(original).toBeTruthy();

	await page.goto(`/items/${item.id}`);
	await page.getByRole('button', { name: 'Duplicate' }).click();
	const dialog = page.getByRole('dialog', { name: 'Duplicate item' });
	const copyName = uniqueName('With cover');
	await dialog.getByLabel('Name').fill(copyName);
	await dialog.getByLabel('Cover image').check();
	const copyId = await submitAndOpenCopy(page, copyName);

	const copied = await coverOf(request, copyId);
	expect(copied).toBeTruthy();
	expect(copied!.id).not.toBe(original!.id);
	expect((await request.get(`/api/v1/media/${copied!.id}/content`)).status()).toBe(200);
	expect(await mediaOf(request, copyId)).toHaveLength(1);

	expect((await request.delete(`/api/v1/media/${copied!.id}`)).ok()).toBeTruthy();
	expect((await request.get(`/api/v1/media/${original!.id}/content`)).status()).toBe(200);
	expect(await coverOf(request, item.id)).toBeTruthy();
});
