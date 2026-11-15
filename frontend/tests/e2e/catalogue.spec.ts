import { test, expect, type APIRequestContext } from './fixtures';

/** Install from catalogue: the dialog on Saved fields adds a ready-made list, and adding again is safe. */
const TITLE = 'Condition grades';

/** Removes any saved list the catalogue entry would have made, so each run starts and ends clean. */
async function removeConditionGrades(request: APIRequestContext) {
	const res = await request.get('/api/v1/presets?kind=choice_list&limit=100');
	expect(res.status(), await res.text()).toBe(200);
	const lists = (await res.json()) as { id: string; label: string }[];
	for (const list of lists.filter((l) => l.label === TITLE)) {
		await request.delete(`/api/v1/presets/${list.id}`);
	}
}

test.beforeEach(async ({ request }) => removeConditionGrades(request));
test.afterEach(async ({ request }) => removeConditionGrades(request));

test('adds a catalogue list to your saved lists and then shows it as added', async ({ page }) => {
	await page.goto('/library/saved-fields');
	await page.getByRole('button', { name: 'Install from catalogue' }).click();

	const dialog = page.getByRole('dialog', { name: 'Install from catalogue' });
	await dialog.getByRole('button', { name: `Install ${TITLE}` }).click();
	// The preview says what will be added; confirming adds it.
	await expect(dialog.getByText('1 saved item')).toBeVisible();
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();

	await expect(page.getByText(/Added 1 saved item/)).toBeVisible();
	await expect(dialog.getByRole('button', { name: `Install ${TITLE}` })).toHaveCount(0);

	await page.keyboard.press('Escape');
	await expect(dialog).toBeHidden();
	// The page row says how many options it has, which the toast and the dialog entry do not.
	const row = page.getByRole('listitem').filter({ hasText: /Condition grades\s*\d+ options/ });
	await expect(row).toBeVisible();
});

test('an entry you already have shows as added and is not made twice', async ({
	page,
	request
}) => {
	for (let attempt = 0; attempt < 2; attempt++) {
		const put = await request.put('/api/v1/catalogue/condition-grades/installation');
		expect(put.status(), await put.text()).toBe(200);
	}

	await page.goto('/library/saved-fields');
	await page.getByRole('button', { name: 'Install from catalogue' }).click();
	const dialog = page.getByRole('dialog', { name: 'Install from catalogue' });
	await expect(dialog.getByText(TITLE, { exact: true })).toBeVisible();
	await expect(dialog.getByRole('button', { name: `Install ${TITLE}` })).toHaveCount(0);

	const res = await request.get('/api/v1/presets?kind=choice_list&limit=100');
	const lists = (await res.json()) as { label: string }[];
	expect(lists.filter((l) => l.label === TITLE)).toHaveLength(1);
});
