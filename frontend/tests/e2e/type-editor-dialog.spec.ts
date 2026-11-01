import { test, expect, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** Item types and relationship types: a compact list, with the editor in a dialog. */
const { makeItemType, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const row = (page: Page, text: string) => page.getByRole('listitem').filter({ hasText: text });

test('New item type opens the editor in a dialog and creates the type', async ({ page }) => {
	const label = uniqueName('Dialog type');
	await page.goto('/settings/item-types');
	await page.getByRole('button', { name: 'New item type', exact: true }).click();
	const dialog = page.getByRole('dialog', { name: 'New item type' });
	await expect(dialog).toBeVisible();
	await dialog.getByLabel('Name').fill(label);
	await dialog.getByRole('button', { name: 'Add item type' }).click();
	await expect(page.getByText('Item type created')).toBeVisible();
	await expect(dialog).toBeHidden();
	await expect(row(page, label)).toBeVisible();
});

test('Edit opens the same editor with the type filled in', async ({ page, request }) => {
	const type = await makeItemType(request, uniqueName('Edit me'));
	await page.goto('/settings/item-types');
	await row(page, type.label).getByRole('button', { name: 'Edit item type' }).click();
	const dialog = page.getByRole('dialog', { name: 'Edit item type' });
	await expect(dialog.getByLabel('Name')).toHaveValue(type.label);
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(page.getByText('Item type updated')).toBeVisible();
	await expect(dialog).toBeHidden();
});

test('Escape on an untouched editor closes it without asking', async ({ page }) => {
	await page.goto('/settings/item-types');
	await page.getByRole('button', { name: 'New item type', exact: true }).click();
	const dialog = page.getByRole('dialog', { name: 'New item type' });
	await expect(dialog).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(dialog).toBeHidden();
	await expect(page.getByRole('group', { name: 'Discard changes?' })).toHaveCount(0);
});

test('closing a changed editor asks before discarding', async ({ page }) => {
	await page.goto('/settings/item-types');
	await page.getByRole('button', { name: 'New item type', exact: true }).click();
	const dialog = page.getByRole('dialog', { name: 'New item type' });
	await dialog.getByLabel('Name').fill('Half written');
	await page.keyboard.press('Escape');
	const ask = dialog.getByRole('group', { name: 'Discard changes?' });
	await expect(ask).toBeVisible();

	await ask.getByRole('button', { name: 'Keep editing' }).click();
	await expect(ask).toBeHidden();
	await expect(dialog.getByLabel('Name')).toHaveValue('Half written');

	await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
	await expect(ask).toBeVisible();
	await ask.getByRole('button', { name: 'Discard', exact: true }).click();
	await expect(dialog).toBeHidden();
});

test('New relationship type opens an editor in a dialog', async ({ page }) => {
	const label = uniqueName('Dialog link');
	await page.goto('/settings/relationships');
	await page.getByRole('button', { name: 'New relationship type', exact: true }).click();
	const dialog = page.getByRole('dialog', { name: 'New relationship type' });
	await expect(dialog).toBeVisible();
	await dialog.getByLabel('Label', { exact: true }).fill(label);
	await dialog.getByRole('button', { name: 'Add relationship type' }).click();
	await expect(page.getByText('Relationship type created')).toBeVisible();
	await expect(dialog).toBeHidden();
	await expect(row(page, label)).toBeVisible();
	// Clean up the type this spec made.
	await row(page, label).getByRole('button', { name: 'Delete relationship type' }).click();
});
