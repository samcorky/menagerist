import { expect, test } from './fixtures';
import { uniqueName } from './helpers';

/**
 * The saved field picker in the item type editor asks the server for its matches, so a saved
 * field past the first hundred is found, by its description too, ignoring accents.
 */
test('the saved field picker searches every saved field on the server', async ({
	page,
	request
}) => {
	test.setTimeout(180_000);
	const word = uniqueName('Picker').replace(/\W+/g, '').toLowerCase();
	const ids: string[] = [];
	const make = async (label: string, description?: string) => {
		const res = await request.post('/api/v1/presets', {
			data: {
				kind: 'field',
				label,
				...(description ? { description } : {}),
				definition: { property: { type: 'string' } }
			}
		});
		expect(res.status(), await res.text()).toBe(201);
		ids.push(((await res.json()) as { id: string }).id);
	};
	try {
		// The picker's first page holds a hundred, oldest first, so the one to find comes last.
		for (let n = 1; n <= 101; n++) await make(`${word} filler ${n}`);
		await make(`${word} grade`, 'How the Café copy looks');

		await page.goto('/library/item-types');
		await page.getByRole('button', { name: 'New item type', exact: true }).click();
		const form = page
			.locator('form')
			.filter({ has: page.getByRole('button', { name: 'Add item type' }) });
		await form.getByRole('button', { name: 'Add from saved fields…' }).click();
		const dialog = page.getByRole('dialog', { name: 'Add from saved fields' });
		const search = dialog.getByLabel('Search saved fields');
		const row = (label: string) => dialog.getByRole('listitem').filter({ hasText: label });

		await expect(dialog.getByRole('listitem').first()).toBeVisible();
		await expect(row(`${word} grade`)).toHaveCount(0);

		// By the description, without the accent, and beyond the first hundred.
		await search.fill('CAFE');
		await expect(row(`${word} grade`)).toBeVisible();
		await expect(row(`${word} filler 1`)).toHaveCount(0);

		// The box stays, and says so, when nothing matches.
		await search.fill('zzz-no-such-saved-field');
		await expect(dialog.getByText('No matches')).toBeVisible();
		await expect(search).toBeEnabled();
	} finally {
		for (const id of ids.reverse()) await request.delete(`/api/v1/presets/${id}`);
	}
});
