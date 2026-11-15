import { test, expect } from './fixtures';
import { uniqueName } from './helpers';

/** Connection types can be saved as a file from their own page. */
test('exports a connection type from its row', async ({ page, request }) => {
	const label = uniqueName('Signed by');
	const created = await request.post('/api/v1/edge-types', {
		data: {
			slug: label.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
			label,
			reverse_label: 'Signed',
			directional: true
		}
	});
	expect(created.status(), await created.text()).toBe(201);
	const id = ((await created.json()) as { id: string }).id;

	try {
		await page.goto('/library/connection-types');
		const row = page.getByRole('listitem').filter({ hasText: label });
		const download = page.waitForEvent('download');
		await row.getByRole('button', { name: 'Export relationship type' }).click();
		const file = await download;

		expect(file.suggestedFilename()).toBe(`${label}.json`);
		const path = await file.path();
		const body = JSON.parse(await (await import('node:fs/promises')).readFile(path, 'utf8')) as {
			version: number;
			relationship_types: { ref: string }[];
		};
		expect(body.version).toBe(3);
		expect(body.relationship_types.map((t) => t.ref)).toEqual([id]);
	} finally {
		await request.delete(`/api/v1/edge-types/${id}`);
	}
});
