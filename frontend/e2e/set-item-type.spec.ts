import { test, expect } from '@playwright/test';
import { createItemType, uniqueName } from './helpers';

test('creates an item type with a field and uses it on a new item', async ({ page }) => {
	const typeLabel = uniqueName('Film');

	await createItemType(page, { label: typeLabel, fields: [{ label: 'Director' }] });

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Back to the Future'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	const directorInput = page.getByLabel('Director');
	await expect(directorInput).toBeVisible();
	await directorInput.fill('Robert Zemeckis');

	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('Director')).toBeVisible();
	await expect(page.getByText('Robert Zemeckis')).toBeVisible();
});
