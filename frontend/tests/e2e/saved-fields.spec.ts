import { test, expect, type APIRequestContext, type Page } from './fixtures';
import { uniqueName } from './helpers';

/** Saved fields: collapsible sections, one More menu for the page-level actions, icon row actions. */
const sectionToggle = (page: Page, name: RegExp) => page.getByRole('button', { name });

/** Saves a list of the person's own through the API and returns its id and unique label. */
async function seedList(request: APIRequestContext) {
	const label = uniqueName('Grades');
	const res = await request.post('/api/v1/presets', {
		data: { kind: 'choice_list', label, definition: { options: ['Mint', 'Good'] } }
	});
	expect(res.status(), await res.text()).toBe(201);
	return { id: ((await res.json()) as { id: string }).id, label };
}

test('sections fold away and stay folded after a reload', async ({ page }) => {
	await page.goto('/library/saved-fields');
	const lists = sectionToggle(page, /^Lists\b/);
	await expect(lists).toHaveAttribute('aria-expanded', 'true');
	await lists.click();
	await expect(lists).toHaveAttribute('aria-expanded', 'false');
	await page.reload();
	await expect(sectionToggle(page, /^Lists\b/)).toHaveAttribute('aria-expanded', 'false');
	await sectionToggle(page, /^Lists\b/).click();
	await expect(sectionToggle(page, /^Lists\b/)).toHaveAttribute('aria-expanded', 'true');
});

test('Import and Export all live in the More menu', async ({ page }) => {
	await page.goto('/library/saved-fields');
	await page.getByRole('button', { name: 'More actions', exact: true }).click();
	await expect(page.getByRole('menuitem', { name: 'Import', exact: true })).toBeVisible();
	await expect(page.getByRole('menuitem', { name: 'Export all', exact: true })).toBeVisible();
	await expect(page.getByRole('menuitemcheckbox')).toHaveCount(0);
});

test('each section has its own import and export icons', async ({ page }) => {
	await page.goto('/library/saved-fields');
	for (const name of ['lists', 'fields', 'field groups']) {
		await expect(page.getByRole('button', { name: `Import ${name}`, exact: true })).toBeVisible();
		await expect(page.getByRole('button', { name: `Export ${name}`, exact: true })).toBeVisible();
	}
});

test('row actions keep their names, with Export and Copy in an overflow menu', async ({
	page,
	request
}) => {
	const list = await seedList(request);
	try {
		await page.goto('/library/saved-fields');
		const row = page.getByRole('listitem').filter({ hasText: list.label });
		await expect(row).toBeVisible();
		await expect(row.getByText('Built-in')).toHaveCount(0);
		await row.getByRole('button', { name: `More actions for ${list.label}` }).click();
		await expect(page.getByRole('menuitem', { name: 'Export', exact: true })).toBeVisible();
		await expect(page.getByRole('menuitem', { name: 'Copy', exact: true })).toBeVisible();
		await page.keyboard.press('Escape');
		await expect(row.getByRole('button', { name: /^Delete / })).toBeEnabled();
	} finally {
		await request.delete(`/api/v1/presets/${list.id}`);
	}
});

test('Try it opens a live example under the row', async ({ page, request }) => {
	const list = await seedList(request);
	try {
		await page.goto('/library/saved-fields');
		const row = page.getByRole('listitem').filter({ hasText: list.label });
		const tryIt = row.getByRole('button', { name: 'Try it' });
		await tryIt.click();
		await expect(tryIt).toHaveAttribute('aria-expanded', 'true');
	} finally {
		await request.delete(`/api/v1/presets/${list.id}`);
	}
});

test('a section with more than ten rows pages with Previous and Next, newest first', async ({
	page,
	request
}) => {
	test.setTimeout(120_000);
	const prefix = uniqueName('Paged').replace(/\W+/g, '');
	const ids: string[] = [];
	try {
		for (let n = 1; n <= 12; n++) {
			const res = await request.post('/api/v1/presets', {
				data: {
					kind: 'choice_list',
					label: `${prefix} ${String(n).padStart(2, '0')}`,
					definition: { options: ['a', 'b'] }
				}
			});
			expect(res.status(), await res.text()).toBe(201);
			ids.push(((await res.json()) as { id: string }).id);
		}

		await page.goto('/library/saved-fields');
		// Other specs share this database, so only the shape of the range is fixed.
		const nav = page.getByRole('navigation', { name: 'Saved list pages' });
		const range = nav.getByTestId('page-range');
		const previous = nav.getByRole('button', { name: 'Previous' });
		const next = nav.getByRole('button', { name: 'Next' });

		await expect(range).toHaveText(/^1–10 (of \d+ )?saved lists$/);
		// Newest first: the last one made leads, and the first one made is on a later page.
		await expect(page.getByRole('listitem').filter({ hasText: `${prefix} 12` })).toBeVisible();
		await expect(previous).toBeDisabled();
		await expect(next).toBeEnabled();
		const shots = process.env.SHOTS_DIR;
		if (shots) {
			await nav.scrollIntoViewIfNeeded();
			await page.screenshot({ path: `${shots}/saved-fields-paged.png` });
		}

		await next.click();
		await expect(range).toHaveText(/^11–\d+ (of \d+ )?saved lists$/);
		await expect(page.getByRole('listitem').filter({ hasText: `${prefix} 12` })).toHaveCount(0);
		await expect(previous).toBeEnabled();

		await previous.click();
		await expect(range).toHaveText(/^1–10 (of \d+ )?saved lists$/);
		await expect(page.getByRole('listitem').filter({ hasText: `${prefix} 12` })).toBeVisible();
	} finally {
		for (const id of ids) await request.delete(`/api/v1/presets/${id}`);
	}
});
