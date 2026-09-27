import { test, expect } from '@playwright/test';
import { createItem, connectToItem, uniqueName } from './helpers';

test('connects one item to another and shows the connection', async ({ page }) => {
	const nameA = uniqueName('Poster');
	const nameB = uniqueName('Signature');

	const urlA = await createItem(page, { name: nameA });
	await createItem(page, { name: nameB });

	await page.goto(urlA);
	await connectToItem(page, { connection: 'related-to', targetName: nameB });

	await expect(page.getByText('No connections yet.')).toHaveCount(0);
	await expect(page.getByRole('link', { name: nameB })).toBeVisible();
});
