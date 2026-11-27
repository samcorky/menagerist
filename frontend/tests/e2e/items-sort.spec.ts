import { expect, test } from './fixtures';
import { uniqueName } from './helpers';

/**
 * The Items toolbar has a sort control (#592). It writes the same sort the Filters dialog
 * edits, which lives in the address, so a link, a reload or Back keeps the order.
 */
test('the Items list can be put in the order a person picks, and keeps it on reload', async ({
	page,
	request
}, testInfo) => {
	test.setTimeout(120_000);
	const prefix = uniqueName('Sortable').replace(/\W+/g, '');
	const names = ['zebra', 'apple', 'mango'].map((word) => `${prefix} ${word}`);
	const ids: string[] = [];
	try {
		// Made in this order, so oldest first is zebra, apple, mango.
		for (const name of names) {
			const res = await request.post('/api/v1/nodes', { data: { name } });
			expect(res.status(), await res.text()).toBe(201);
			ids.push(((await res.json()) as { id: string }).id);
		}

		await page.goto('/items');
		await page.getByPlaceholder('Search your items…').fill(prefix);
		const sort = page.getByLabel('Sort by');
		const rows = page.getByRole('link').filter({ hasText: prefix });
		const order = async () =>
			(await rows.allInnerTexts()).map((text) => names.findIndex((name) => text.includes(name)));
		const expectOrder = async (words: string[]) => {
			await expect
				.poll(order)
				.toEqual(words.map((word) => names.findIndex((name) => name.endsWith(word))));
		};

		await expectOrder(['zebra', 'apple', 'mango']);
		await expect(sort).toHaveValue('oldest');

		await sort.selectOption({ label: 'Newest first' });
		await expectOrder(['mango', 'apple', 'zebra']);
		const shots = process.env.SHOTS_DIR;
		if (shots) await page.screenshot({ path: `${shots}/items-sort-${testInfo.project.name}.png` });

		await sort.selectOption({ label: 'Name A to Z' });
		await expectOrder(['apple', 'mango', 'zebra']);

		await sort.selectOption({ label: 'Name Z to A' });
		await expectOrder(['zebra', 'mango', 'apple']);

		// The order is in the address, so a reload keeps it and the control shows it.
		await page.reload();
		await expect(sort).toHaveValue('name-desc');
		await expectOrder(['zebra', 'mango', 'apple']);

		await sort.selectOption({ label: 'Oldest first' });
		await expectOrder(['zebra', 'apple', 'mango']);
	} finally {
		for (const id of ids) await request.delete(`/api/v1/nodes/${id}`);
	}
});
