import { test, expect } from './fixtures';
import { uniqueName } from './helpers';

/** Item types can be saved as a file with the lists they use, and imported on the Saved fields page. */
test('exports an item type with the list its field uses', async ({ page, request }) => {
	const listLabel = uniqueName('Grades');
	const typeLabel = uniqueName('Record');
	const list = await request.post('/api/v1/presets', {
		data: { kind: 'choice_list', label: listLabel, definition: { options: ['Mint', 'Good'] } }
	});
	expect(list.status(), await list.text()).toBe(201);
	const listId = ((await list.json()) as { id: string }).id;
	const type = await request.post('/api/v1/node-types', {
		data: {
			label: typeLabel,
			slug: typeLabel.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
			attributes_schema: {
				type: 'object',
				properties: {
					condition: {
						type: 'string',
						title: 'Condition',
						'x-menagerist': { kind: 'choice', list: listId }
					}
				}
			}
		}
	});
	expect(type.status(), await type.text()).toBe(201);
	const typeId = ((await type.json()) as { id: string }).id;

	try {
		await page.goto('/library/item-types');
		const row = page.getByRole('listitem').filter({ hasText: typeLabel });
		const download = page.waitForEvent('download');
		await row.getByRole('button', { name: 'Export item type' }).click();
		const file = await download;

		expect(file.suggestedFilename()).toBe(`${typeLabel}.json`);
		const path = await file.path();
		const body = JSON.parse(await (await import('node:fs/promises')).readFile(path, 'utf8')) as {
			version: number;
			item_types: { ref: string }[];
			presets: { ref: string; label: string }[];
		};
		expect(body.version).toBe(2);
		expect(body.item_types.map((t) => t.ref)).toEqual([typeId]);
		expect(body.presets.map((p) => [p.ref, p.label])).toEqual([[listId, listLabel]]);
	} finally {
		await request.delete(`/api/v1/node-types/${typeId}`);
		await request.delete(`/api/v1/presets/${listId}`);
	}
});

/** Several item types can be picked and saved as one file. */
test('exports the selected item types together', async ({ page, request }) => {
	const labels = [uniqueName('Record'), uniqueName('Sleeve'), uniqueName('Poster')];
	const ids: string[] = [];
	for (const label of labels) {
		const res = await request.post('/api/v1/node-types', {
			data: {
				label,
				slug: label.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
				attributes_schema: { type: 'object', properties: {} }
			}
		});
		expect(res.status(), await res.text()).toBe(201);
		ids.push(((await res.json()) as { id: string }).id);
	}

	try {
		await page.goto('/library/item-types');
		await page.getByRole('checkbox', { name: `Select ${labels[0]}` }).click();
		await page.getByRole('checkbox', { name: `Select ${labels[2]}` }).click();
		await expect(page.getByText('2 item types selected')).toBeVisible();

		const download = page.waitForEvent('download');
		await page.getByRole('button', { name: 'Export 2 item types' }).click();
		const file = await download;

		expect(file.suggestedFilename()).toBe('Item types.json');
		const path = await file.path();
		const body = JSON.parse(await (await import('node:fs/promises')).readFile(path, 'utf8')) as {
			item_types: { ref: string }[];
		};
		expect(body.item_types.map((t) => t.ref).sort()).toEqual([ids[0], ids[2]].sort());
		await expect(page.getByText('2 item types selected')).toHaveCount(0);
	} finally {
		for (const id of ids) await request.delete(`/api/v1/node-types/${id}`);
	}
});
