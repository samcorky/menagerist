import { test, expect, type Page } from './fixtures';

/** Saved fields: collapsible sections, one More menu for the page-level actions, icon row actions. */
const sectionToggle = (page: Page, name: RegExp) => page.getByRole('button', { name });

async function showBuiltIns(page: Page) {
	await page.getByRole('button', { name: 'More actions', exact: true }).click();
	const toggle = page.getByRole('menuitemcheckbox', { name: /Show built-in/ });
	if ((await toggle.getAttribute('aria-checked')) !== 'true') await toggle.click();
	else await page.keyboard.press('Escape');
}

test('sections fold away and stay folded after a reload', async ({ page }) => {
	await page.goto('/settings/saved-fields');
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
	await page.goto('/settings/saved-fields');
	await page.getByRole('button', { name: 'More actions', exact: true }).click();
	await expect(page.getByRole('menuitem', { name: 'Import', exact: true })).toBeVisible();
	await expect(page.getByRole('menuitem', { name: 'Export all', exact: true })).toBeVisible();
	await expect(page.getByRole('menuitemcheckbox', { name: /Show built-in/ })).toBeVisible();
});

test('each section has its own import and export icons', async ({ page }) => {
	await page.goto('/settings/saved-fields');
	for (const name of ['lists', 'fields', 'field groups']) {
		await expect(page.getByRole('button', { name: `Import ${name}`, exact: true })).toBeVisible();
		await expect(page.getByRole('button', { name: `Export ${name}`, exact: true })).toBeVisible();
	}
});

test('row actions keep their names, with Export and Copy in an overflow menu', async ({ page }) => {
	await page.goto('/settings/saved-fields');
	await showBuiltIns(page);
	const row = page
		.getByRole('listitem')
		.filter({ has: page.getByRole('button', { name: 'Try it' }) });
	await expect(row.first()).toBeVisible();
	await expect(row.first().getByRole('button', { name: /^More actions for / })).toBeVisible();
	await row
		.first()
		.getByRole('button', { name: /^More actions for / })
		.click();
	await expect(page.getByRole('menuitem', { name: 'Export', exact: true })).toBeVisible();
	await expect(page.getByRole('menuitem', { name: 'Copy', exact: true })).toBeVisible();
	await page.keyboard.press('Escape');
	// Built-in rows cannot be deleted, and say why.
	await expect(row.first().getByRole('button', { name: /^Delete / })).toBeDisabled();
});

test('Try it opens a live example under the row', async ({ page }) => {
	await page.goto('/settings/saved-fields');
	await showBuiltIns(page);
	const tryIt = page.getByRole('button', { name: 'Try it' }).first();
	await tryIt.click();
	await expect(tryIt).toHaveAttribute('aria-expanded', 'true');
});
