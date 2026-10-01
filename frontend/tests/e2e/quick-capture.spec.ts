import { test, expect } from '@playwright/test';
import { openQuickCapture, uniqueName } from './helpers';

test('captures an item from the quick capture dialog', async ({ page }) => {
	const name = uniqueName('Quick capture item');

	await page.goto('/');
	const dialog = await openQuickCapture(page);

	await dialog.getByPlaceholder('Name…').fill(name);
	await dialog.getByRole('button', { name: /^Saving…$|^Save$/ }).click();
	await expect(dialog).toBeHidden();

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill(name);
	await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
});
