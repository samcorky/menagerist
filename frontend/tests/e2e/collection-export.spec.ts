import { readFile } from 'node:fs/promises';
import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

const { makeCollection, makeItem, makeItemType, addToCollection, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

/** A collection can be saved as a file from its own page, with the items on it. */
test('exports a collection with its items and their type', async ({ page, request }) => {
	const type = await makeItemType(request, uniqueName('Record'));
	const first = await makeItem(request, uniqueName('Kind of Blue'), type.slug);
	const second = await makeItem(request, uniqueName('A Love Supreme'), type.slug);
	const collection = await makeCollection(request, uniqueName('Jazz'), 'Blue notes');
	await addToCollection(request, collection.id, [first.id, second.id]);

	await page.goto(`/collections/${collection.id}`);
	const download = page.waitForEvent('download');
	await page.getByRole('button', { name: 'Export', exact: true }).click();
	const file = await download;

	expect(file.suggestedFilename()).toBe(`${collection.name}.json`);
	const body = JSON.parse(await readFile(await file.path(), 'utf8')) as {
		version: number;
		collections: { name: string; description: string; item_refs: string[] }[];
		items: { ref: string }[];
		item_types: { ref: string }[];
	};
	expect(body.version).toBe(3);
	expect(body.collections.map((c) => [c.name, c.description])).toEqual([
		[collection.name, 'Blue notes']
	]);
	expect([...body.collections[0].item_refs].sort()).toEqual([first.id, second.id].sort());
	expect(body.items.map((i) => i.ref).sort()).toEqual([first.id, second.id].sort());
	expect(body.item_types.map((t) => t.ref)).toEqual([type.id]);
});
