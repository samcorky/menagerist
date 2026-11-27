import { expect, test } from './fixtures';
import { uniqueName } from './helpers';

/**
 * The Item types search asks the server (#792), so it finds a type on a page the list has not
 * scrolled to, and each match comes with its family: a parent brings its subtypes, a subtype
 * brings its parent.
 */
test('searching item types matches on the server and shows each match with its family', async ({
	page,
	request
}) => {
	test.setTimeout(120_000);
	const base = uniqueName('Srch').replace(/\W+/g, '').toLowerCase();
	const ids: string[] = [];
	const make = async (slug: string, label: string, parent?: string) => {
		const res = await request.post('/api/v1/node-types', {
			data: { slug, label, ...(parent ? { parent } : {}) }
		});
		expect(res.status(), await res.text()).toBe(201);
		ids.push(((await res.json()) as { id: string }).id);
	};
	try {
		await make(`${base}-parent`, `${base} Parent`);
		await make(`${base}-alpha`, `${base} Alpha`, `${base}-parent`);
		await make(`${base}-beta`, `${base} Beta`, `${base}-parent`);
		// Enough types for the search box to show, one of them with an accent to find without it.
		await make(`${base}-cafe`, `${base} Café`);
		for (let n = 1; n <= 9; n++) await make(`${base}-fill-${n}`, `${base} Fill ${n}`);

		await page.goto('/library/item-types');
		const search = page.getByPlaceholder('Search item types…');
		// A row's own checkbox names it exactly; a subtype's row also mentions its parent in text.
		const row = (label: string) => page.getByLabel(`Select ${base} ${label}`, { exact: true });

		// A subtype brings its parent, and not the parent's other subtypes.
		await search.fill(`${base} Alpha`);
		await expect(row('Alpha')).toHaveCount(1);
		await expect(row('Parent')).toHaveCount(1);
		await expect(row('Beta')).toHaveCount(0);
		// The box stays while the search has narrowed the list to a few rows.
		await expect(search).toBeVisible();

		// A parent brings every subtype.
		await search.fill(`${base} Parent`);
		await expect(row('Alpha')).toHaveCount(1);
		await expect(row('Beta')).toHaveCount(1);
		await expect(row('Parent')).toHaveCount(1);

		// The server ignores accents.
		await search.fill(`${base} cafe`);
		await expect(row('Café')).toHaveCount(1);
		await expect(row('Fill 1')).toHaveCount(0);

		await search.fill('zzz-nothing-matches');
		await expect(page.getByText('No item types match "zzz-nothing-matches".')).toBeVisible();
		await expect(page.getByText('No item types yet')).toHaveCount(0);

		await search.fill('');
		await expect(row('Fill 1')).toBeVisible();
	} finally {
		for (const id of ids.reverse()) await request.delete(`/api/v1/node-types/${id}`);
	}
});
