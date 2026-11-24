import { test, expect, type Locator, type Page } from './fixtures';

/** Mobile sheets close when their grab bar is dragged down, through the same checks as Close. */

async function drag(page: Page, dialog: Locator, dy: number, steps: number) {
	const box = await dialog.locator('[data-slot="sheet-grab-bar"] > div').boundingBox();
	if (!box) throw new Error('grab bar not visible');
	const x = box.x + box.width / 2;
	const y = box.y + box.height / 2;
	await page.mouse.move(x, y);
	await page.mouse.down();
	await page.mouse.move(x, y + dy, { steps });
	await page.mouse.up();
}

async function openTypeEditor(page: Page) {
	await page.goto('/library/item-types');
	await page.getByRole('button', { name: 'New item type', exact: true }).click();
	const dialog = page.getByRole('dialog', { name: 'New item type' });
	await expect(dialog).toBeVisible();
	// The sheet slides in over 250 ms. Grabbing the bar mid-slide aims at where it was, not where
	// it is, so the drag misses it on a slow runner.
	await dialog.evaluate((el) => Promise.all(el.getAnimations().map((a) => a.finished)));
	return dialog;
}

test('dragging the grab bar far enough closes the sheet', async ({ page }) => {
	const dialog = await openTypeEditor(page);
	await drag(page, dialog, 400, 20);
	await expect(dialog).toBeHidden();
});

test('a short, slow drag springs the sheet back', async ({ page }) => {
	const dialog = await openTypeEditor(page);
	await drag(page, dialog, 40, 20);
	await expect(dialog).toBeVisible();
	await expect(dialog).toHaveCSS('transform', 'none');
});

test('dragging a sheet with unsaved changes asks before discarding', async ({ page }) => {
	const dialog = await openTypeEditor(page);
	await dialog.getByLabel('Name').fill('Half written');
	await drag(page, dialog, 400, 20);

	const ask = dialog.getByRole('group', { name: 'Discard changes?' });
	await expect(ask).toBeVisible();
	await expect(dialog).toHaveCSS('transform', 'none');
	await ask.getByRole('button', { name: 'Keep editing' }).click();
	await expect(dialog.getByLabel('Name')).toHaveValue('Half written');
});
