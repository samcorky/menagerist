import { test, expect, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** Item types and relationship types: a compact list, with the editor in a dialog. */
const { makeItemType, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const row = (page: Page, text: string) => page.getByRole('listitem').filter({ hasText: text });

test('New item type opens the editor in a dialog and creates the type', async ({ page }) => {
	const label = uniqueName('Dialog type');
	await page.goto('/library/item-types');
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
	await page.goto('/library/item-types');
	await row(page, type.label).getByRole('button', { name: 'Edit item type' }).click();
	const dialog = page.getByRole('dialog', { name: 'Edit item type' });
	await expect(dialog.getByLabel('Name')).toHaveValue(type.label);
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(page.getByText('Item type updated')).toBeVisible();
	await expect(dialog).toBeHidden();
});

test('Escape on an untouched editor closes it without asking', async ({ page }) => {
	await page.goto('/library/item-types');
	await page.getByRole('button', { name: 'New item type', exact: true }).click();
	const dialog = page.getByRole('dialog', { name: 'New item type' });
	await expect(dialog).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(dialog).toBeHidden();
	await expect(page.getByRole('group', { name: 'Discard changes?' })).toHaveCount(0);
});

test('closing a changed editor asks before discarding', async ({ page }) => {
	await page.goto('/library/item-types');
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

// A schema as the API holds it for a type made by a script: one plain field, none of the layout
// or version the schema editor adds when it opens.
const oneField = {
	type: 'object',
	properties: { rating: { type: 'string', title: 'Rating', 'x-menagerist': { kind: 'text' } } }
};

test('cancelling an untouched editor of a type with fields closes it without asking', async ({
	page,
	request
}) => {
	const label = uniqueName('Has a field');
	const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
	const made = await request.post('/api/v1/node-types', {
		data: { slug, label, attributes_schema: oneField }
	});
	expect(made.status(), await made.text()).toBe(201);
	const { id } = (await made.json()) as { id: string };

	await page.goto('/library/item-types');
	await row(page, label).getByRole('button', { name: 'Edit item type' }).click();
	const dialog = page.getByRole('dialog', { name: 'Edit item type' });
	await expect(dialog.getByLabel('Name')).toHaveValue(label);
	// The schema editor has opened the field; give it time to settle before asking to leave.
	await expect(dialog.getByLabel('Field label').first()).toHaveValue('Rating');
	await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
	await expect(dialog).toBeHidden();
	await expect(page.getByRole('group', { name: 'Discard changes?' })).toHaveCount(0);

	// A real change to the same type still asks.
	await row(page, label).getByRole('button', { name: 'Edit item type' }).click();
	await expect(dialog.getByLabel('Field label').first()).toHaveValue('Rating');
	await dialog.getByLabel('Name').fill(`${label} changed`);
	await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
	await expect(dialog.getByRole('group', { name: 'Discard changes?' })).toBeVisible();
	await dialog
		.getByRole('group', { name: 'Discard changes?' })
		.getByRole('button', { name: 'Discard', exact: true })
		.click();
	await expect(dialog).toBeHidden();
	await request.delete(`/api/v1/node-types/${id}`);
});

test('cancelling an untouched editor of a relationship type with fields closes it without asking', async ({
	page,
	request
}) => {
	const label = uniqueName('Link with a field');
	const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
	const made = await request.post('/api/v1/edge-types', {
		data: { slug, label, attributes_schema: oneField }
	});
	expect(made.status(), await made.text()).toBe(201);
	const { id } = (await made.json()) as { id: string };

	await page.goto('/library/connection-types');
	await row(page, label).getByRole('button', { name: 'Edit relationship type' }).click();
	const dialog = page.getByRole('dialog', { name: 'Edit relationship type' });
	await expect(dialog.getByLabel('Field label').first()).toHaveValue('Rating');
	await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
	await expect(dialog).toBeHidden();
	await expect(page.getByRole('group', { name: 'Discard changes?' })).toHaveCount(0);
	await request.delete(`/api/v1/edge-types/${id}`);
});

test('New relationship type opens an editor in a dialog', async ({ page }) => {
	const label = uniqueName('Dialog link');
	await page.goto('/library/connection-types');
	await page.getByRole('button', { name: 'New relationship type', exact: true }).click();
	const dialog = page.getByRole('dialog', { name: 'New relationship type' });
	await expect(dialog).toBeVisible();
	await dialog.getByLabel('Label', { exact: true }).fill(label);
	await dialog.getByRole('button', { name: 'Add relationship type' }).click();
	await expect(page.getByText('Connection type created')).toBeVisible();
	await expect(dialog).toBeHidden();
	await expect(row(page, label)).toBeVisible();
	// Clean up the type this spec made.
	await row(page, label).getByRole('button', { name: 'Delete relationship type' }).click();
});
