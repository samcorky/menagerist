import { test, expect } from './fixtures';
import { openQuickCapture, openSearch } from './helpers';

/**
 * The system Back gesture on a phone: it closes an open sheet first, adds no extra history
 * entries, and the in-page Back button never leaves the app.
 */

test('Back closes the quick capture sheet and stays on the page', async ({ page }) => {
	await page.goto('/items');
	const dialog = await openQuickCapture(page);

	await page.goBack();

	await expect(dialog).toBeHidden();
	await expect(page).toHaveURL(/\/items$/);
});

test('Back closes the search sheet and stays on the page', async ({ page }) => {
	await page.goto('/items');
	await openSearch(page);

	await page.goBack();

	await expect(page.getByRole('dialog', { name: 'Search' })).toBeHidden();
	await expect(page).toHaveURL(/\/items$/);
});

test('closing a sheet with its button leaves no extra history entry', async ({ page }) => {
	await page.goto('/');
	await page.goto('/items');
	const dialog = await openQuickCapture(page);

	await dialog.getByRole('button', { name: 'Close' }).tap();
	await expect(dialog).toBeHidden();
	await page.goBack();

	await expect(page).toHaveURL(/\/$/);
});

test('the Back button on a page opened directly goes to its parent, not out of the app', async ({
	page
}) => {
	await page.goto('/collections/not-a-real-collection');
	await page.getByRole('button', { name: 'Back' }).tap();

	await expect(page).toHaveURL(/\/collections$/);
});
