import { test, expect } from '@playwright/test';
import { createItem, uniqueName } from './helpers';

test('creates an item and lands on its page', async ({ page }) => {
	const name = uniqueName('Poster');

	await createItem(page, { name });

	await expect(page).toHaveURL(/\/items\/(?!new$)[^/]+$/);
	await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
});
