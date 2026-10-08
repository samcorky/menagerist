import { test, expect } from './fixtures';
import { createItemType, addFieldToItemType, uniqueName } from './helpers';

test('creates an item type, then edits it and persists the change', async ({ page }) => {
	const label = uniqueName('Manage type');

	await createItemType(page, { label, fields: [{ label: 'Colour' }] });
	await addFieldToItemType(page, { label: 'Size' });

	// Reload to prove the second field actually persisted server-side, not just
	// client-side state - then re-locate the card by its unique label so this
	// doesn't depend on list ordering. Scoped to the card's own `[data-slot="card"]`
	// boundary, not a generic `div` filter - other item types in the shared list
	// (from other specs) also nest inside ancestor divs that "contain" this label's
	// text once concatenated, which previously made `.first()` grab the wrong
	// type's "Edit item type" button.
	await page.reload();
	const card = page.locator('[data-slot="card"]').filter({ hasText: label });
	await expect(card).toHaveCount(1);
	await card.getByRole('button', { name: 'Edit item type' }).click();

	const fieldLabels = page.getByLabel('Field label');
	await expect(fieldLabels).toHaveCount(2);
	await expect(fieldLabels.nth(0)).toHaveValue('Colour');
	await expect(fieldLabels.nth(1)).toHaveValue('Size');
});
