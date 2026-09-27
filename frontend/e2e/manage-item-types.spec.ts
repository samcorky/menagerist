import { test, expect } from '@playwright/test';
import { createItemType, addFieldToItemType, uniqueName } from './helpers';

test('creates an item type, then edits it and persists the change', async ({ page }) => {
	const label = uniqueName('Manage type');

	await createItemType(page, { label, fields: [{ label: 'Colour' }] });
	await addFieldToItemType(page, { label: 'Size' });

	// Reload to prove the second field actually persisted server-side, not just
	// client-side state - then re-locate the card by its unique label so this
	// doesn't depend on list ordering.
	await page.reload();
	const card = page.locator('div').filter({ hasText: label });
	await card.getByRole('button', { name: 'Edit item type' }).first().click();

	const fieldLabels = page.getByLabel('Field label');
	await expect(fieldLabels).toHaveCount(2);
	await expect(fieldLabels.nth(0)).toHaveValue('Colour');
	await expect(fieldLabels.nth(1)).toHaveValue('Size');
});
