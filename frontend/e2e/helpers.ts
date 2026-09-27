import { expect, type Page } from '@playwright/test';

/**
 * Reusable flows shared across e2e specs. Each helper drives the real UI (no
 * API shortcuts) so every spec exercises the same paths a user would.
 */

/** A name that's unique per call, so tests never collide with earlier runs against the same db. */
export function uniqueName(prefix: string): string {
	return `${prefix} ${Date.now()}-${Math.floor(Math.random() * 100_000)}`;
}

export type FieldSpec = {
	label: string;
};

/** Creates an item type from Settings > Item types, optionally with fields, and returns its label. */
export async function createItemType(
	page: Page,
	options: { label: string; description?: string; fields?: FieldSpec[] }
): Promise<{ label: string }> {
	await page.goto('/settings/item-types');

	const form = page
		.locator('form')
		.filter({ has: page.getByRole('button', { name: 'Add item type' }) });
	await form.getByLabel('Name').fill(options.label);
	if (options.description) {
		await form.getByLabel('Description').fill(options.description);
	}

	for (const field of options.fields ?? []) {
		await form.getByRole('button', { name: 'Add field', exact: true }).click();
		await form.getByLabel('Field label').last().fill(field.label);
	}

	await form.getByRole('button', { name: 'Add item type' }).click();
	await expect(page.getByText('Item type created')).toBeVisible();
	await expect(page.getByText(options.label, { exact: true }).first()).toBeVisible();

	return { label: options.label };
}

/**
 * Adds a field to the item type edit form that is currently open on the Item
 * types page. Must be called right after `createItemType`, with no
 * navigation in between: newly created types are prepended to the top of
 * the (client-only) list, so `.first()` reliably targets the one just
 * created regardless of what other tests are doing to the shared database.
 */
export async function addFieldToItemType(page: Page, field: FieldSpec): Promise<void> {
	await page.getByRole('button', { name: 'Edit item type' }).first().click();

	const editForm = page
		.locator('form')
		.filter({ has: page.getByRole('button', { name: /^Saving…$|^Save$/ }) });
	await editForm.getByRole('button', { name: 'Add field', exact: true }).click();
	await editForm.getByLabel('Field label').last().fill(field.label);
	await editForm.getByRole('button', { name: /^Saving…$|^Save$/ }).click();
	await expect(page.getByText('Item type updated')).toBeVisible();
}

/** Creates an item from the full "New item" form and returns the resulting item detail URL. */
export async function createItem(
	page: Page,
	options: { name: string; type?: string }
): Promise<string> {
	await page.goto('/items/new');
	await page.getByLabel('Name').fill(options.name);

	if (options.type) {
		await page.getByPlaceholder('Search item types…').fill(options.type);
		await page.getByRole('button', { name: options.type, exact: true }).click();
	}

	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);
	return page.url();
}

/** Connects the currently-open item to another item by name via the "Connect item" form. */
export async function connectToItem(
	page: Page,
	options: { connection: string; targetName: string }
): Promise<void> {
	await page.getByLabel('Connection').fill(options.connection);

	const targetSearch = page.getByPlaceholder('Search items…');
	await targetSearch.fill(options.targetName);
	await page
		.getByRole('button', { name: new RegExp(options.targetName) })
		.first()
		.click();

	// Selecting a target keeps the search input focused, so its dropdown stays
	// open (it only closes ~150ms after blur) and would otherwise overlap the
	// submit button below it.
	await targetSearch.blur();
	await page.waitForTimeout(250);

	await page.getByRole('button', { name: /^Connect items?$/ }).click();
}

/**
 * Opens the quick capture dialog via its global keyboard shortcut. Waits for
 * the app shell to hydrate first - this is a client-rendered SPA, so the
 * keydown listener isn't attached until Svelte has mounted.
 */
export async function openQuickCapture(page: Page) {
	await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
	await page.keyboard.press('Control+k');
	const dialog = page.getByRole('dialog', { name: 'Quick capture' });
	await expect(dialog).toBeVisible();
	return dialog;
}
