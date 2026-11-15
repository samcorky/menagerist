import { readFile } from 'node:fs/promises';
import { test, expect } from './fixtures';
import { uniqueName } from './helpers';

/** An item can be saved as a file from its own page, with the type it uses. */
test('exports an item with its type', async ({ page, request }) => {
	const typeLabel = uniqueName('Record');
	const itemName = uniqueName('Kind of Blue');
	const type = await request.post('/api/v1/node-types', {
		data: {
			label: typeLabel,
			slug: typeLabel.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
			attributes_schema: {
				type: 'object',
				properties: { year: { type: 'integer', title: 'Year' } }
			}
		}
	});
	expect(type.status(), await type.text()).toBe(201);
	const { id: typeId, slug: typeSlug } = (await type.json()) as { id: string; slug: string };
	const item = await request.post('/api/v1/nodes', {
		data: { name: itemName, type: typeSlug, attributes: { year: 1959 }, tags: ['jazz'] }
	});
	expect(item.status(), await item.text()).toBe(201);
	const itemId = ((await item.json()) as { id: string }).id;

	try {
		await page.goto(`/items/${itemId}`);
		const download = page.waitForEvent('download');
		await page.getByRole('button', { name: 'Export', exact: true }).click();
		const file = await download;

		expect(file.suggestedFilename()).toBe(`${itemName}.json`);
		const body = JSON.parse(await readFile(await file.path(), 'utf8')) as {
			version: number;
			items: { ref: string; name: string; type_ref: string | null; attributes: object }[];
			item_types: { ref: string }[];
		};
		expect(body.version).toBe(3);
		expect(body.items.map((i) => [i.ref, i.name, i.type_ref])).toEqual([
			[itemId, itemName, typeId]
		]);
		expect(body.items[0].attributes).toEqual({ year: 1959 });
		expect(body.item_types.map((t) => t.ref)).toEqual([typeId]);
	} finally {
		await request.delete(`/api/v1/nodes/${itemId}`);
		await request.delete(`/api/v1/node-types/${typeId}`);
	}
});
