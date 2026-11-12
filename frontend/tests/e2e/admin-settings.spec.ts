import { expect, test } from './fixtures';

/**
 * Instance settings: change a value, see it survive a reload, be refused a bad one,
 * and put it back. The worker's own backend and database make the change safe.
 */
test.describe.configure({ mode: 'serial' });

test('an administrator changes a setting, keeps it across a reload and resets it', async ({
	page
}) => {
	await page.goto('/admin');
	await page.locator('main a[href="/admin/settings"]').click();
	await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();

	const card = page.getByRole('listitem').filter({
		has: page.getByRole('heading', { name: 'Backups to keep', exact: true })
	});
	const field = page.getByLabel('Backups to keep', { exact: true });
	await expect(card.getByText('Default', { exact: true })).toBeVisible();
	await expect(card.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0);

	await field.fill('3');
	await card.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(page.getByText('Saved', { exact: true })).toBeVisible();
	await expect(card.getByText('Changed here', { exact: true })).toBeVisible();
	await expect(card.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0);

	await page.reload();
	await expect(page.getByLabel('Backups to keep', { exact: true })).toHaveValue('3');

	await card.getByRole('button', { name: 'Reset to default' }).click();
	await expect(
		page.locator('[data-sonner-toast]').getByText('Reset to default', { exact: true })
	).toBeVisible();
	await expect(card.getByText('Default', { exact: true })).toBeVisible();
	await expect(page.getByLabel('Backups to keep', { exact: true })).toHaveValue('7');
});

test('a value the rules refuse is explained next to the setting and nothing is saved', async ({
	page
}) => {
	await page.goto('/admin/settings');
	const card = page.getByRole('listitem').filter({
		has: page.getByRole('heading', { name: 'Backups to keep', exact: true })
	});

	await page.getByLabel('Backups to keep', { exact: true }).fill('0');
	await card.getByRole('button', { name: 'Save', exact: true }).click();

	await expect(card.getByRole('alert')).toBeVisible();
	await page.reload();
	await expect(page.getByLabel('Backups to keep', { exact: true })).toHaveValue('7');
	await expect(card.getByText('Default', { exact: true })).toBeVisible();
});

test('discarding an edit puts the saved value back without saving', async ({ page }) => {
	await page.goto('/admin/settings');
	const card = page.getByRole('listitem').filter({
		has: page.getByRole('heading', { name: 'Backups to keep', exact: true })
	});
	const field = page.getByLabel('Backups to keep', { exact: true });

	await field.fill('5');
	await card.getByRole('button', { name: 'Discard' }).click();

	await expect(field).toHaveValue('7');
	await expect(card.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0);
});

test('one section shows at a time and the section is in the link', async ({ page }) => {
	await page.goto('/admin/settings');
	const section = page.getByRole('navigation', { name: 'Settings sections' });
	await expect(page.getByRole('heading', { name: 'Backups', exact: true })).toBeVisible();
	await expect(page.getByLabel('Backups to keep', { exact: true })).toBeVisible();

	await section.getByRole('link', { name: /^Scheduled tasks/ }).click();
	await expect(page).toHaveURL(/\?section=scheduler/);
	await expect(page.getByRole('heading', { name: 'Scheduled tasks', exact: true })).toBeVisible();
	await expect(page.getByLabel('Backups to keep', { exact: true })).toHaveCount(0);
	await expect(section.getByRole('link', { name: /^Scheduled tasks/ })).toHaveAttribute(
		'aria-current',
		'page'
	);

	await page.goBack();
	await expect(page.getByLabel('Backups to keep', { exact: true })).toBeVisible();
});

test('a link to one setting opens its section and highlights it', async ({ page }) => {
	await page.goto('/admin/settings#setting-backup.keep_last');
	const heading = page.getByRole('heading', { name: 'Backups to keep', exact: true });
	await expect(heading).toBeVisible();
	await expect(heading).toBeFocused();
	await expect(page.getByRole('listitem').filter({ has: heading })).toHaveClass(/bg-accent/);
});

test('an unknown section falls back to the first', async ({ page }) => {
	await page.goto('/admin/settings?section=nope');
	await expect(page.getByLabel('Backups to keep', { exact: true })).toBeVisible();
});

test('Save and Discard only appear while a value differs from the saved one', async ({ page }) => {
	await page.goto('/admin/settings');
	const row = page.getByRole('listitem').filter({
		has: page.getByRole('heading', { name: 'Backups to keep', exact: true })
	});
	const field = page.getByLabel('Backups to keep', { exact: true });

	await expect(row.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0);
	await field.fill('5');
	await expect(row.getByRole('button', { name: 'Save', exact: true })).toHaveCount(1);
	await expect(row.getByRole('button', { name: 'Discard', exact: true })).toHaveCount(1);
	await field.fill('7');
	await expect(row.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0);
});
