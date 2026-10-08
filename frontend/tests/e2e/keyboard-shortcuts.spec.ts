import { test, expect } from './fixtures';
import { createItem, createItemType, uniqueName } from './helpers';

test('g c / g s / g e navigate between the main sections', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();

	await page.keyboard.press('g');
	await page.keyboard.press('c');
	await expect(page).toHaveURL(/\/items$/);
	// Pages register their own shortcuts as they mount, which rebinds the
	// listener and drops a half-typed sequence - so let each page settle first.
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();

	await page.keyboard.press('g');
	await page.keyboard.press('s');
	await expect(page).toHaveURL(/\/settings$/);
	await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();

	await page.keyboard.press('g');
	await page.keyboard.press('e');
	await expect(page).toHaveURL(/\/explore$/);
	await expect(page.getByRole('heading', { name: 'Explore' })).toBeVisible();
});

test('an abandoned g-sequence does not block typing a literal "g"', async ({ page }) => {
	await page.goto('/items');
	await page.keyboard.press('g');
	// Pause past the sequence-reset window, then type into the search box.
	await page.waitForTimeout(1200);
	const search = page.getByPlaceholder('Search your items…');
	await search.fill('vintage gramophone');
	await expect(search).toHaveValue('vintage gramophone');
});

test('/ focuses search on the items page, and navigates there from elsewhere', async ({ page }) => {
	await page.goto('/items');
	await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
	await page.keyboard.press('/');
	await expect(page.getByPlaceholder('Search your items…')).toBeFocused();

	await page.goto('/settings');
	await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
	await page.keyboard.press('/');
	await expect(page).toHaveURL(/\/items(\?search=1)?$/);
	await expect(page.getByPlaceholder('Search your items…')).toBeFocused();
});

test('? opens the shortcuts help overlay', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
	await page.keyboard.press('Shift+?');
	const dialog = page.getByRole('dialog', { name: 'Keyboard shortcuts' });
	await expect(dialog).toBeVisible();
	await expect(dialog.getByText('Quick capture').first()).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(dialog).toBeHidden();
});

test('e / Esc / Cmd+S drive edit mode on an item', async ({ page }) => {
	const name = uniqueName('Shortcut item');
	await createItem(page, { name });
	// The edit shortcut only exists once the item has loaded, in read mode.
	const editButton = page.getByRole('button', { name: 'Edit', exact: true });
	await expect(editButton).toBeVisible();

	await page.keyboard.press('e');
	const nameInput = page.getByLabel('Name');
	await expect(nameInput).toBeVisible();

	// Escape is ignored while a text field has focus, so leave the field first.
	await nameInput.fill(`${name} (edited, then cancelled)`);
	await nameInput.blur();
	await page.keyboard.press('Escape');
	await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
	await expect(page.getByText(`${name} (edited, then cancelled)`)).toHaveCount(0);
	await expect(editButton).toBeVisible();

	await page.keyboard.press('e');
	await page.getByLabel('Name').fill(`${name} (saved)`);
	await page.keyboard.press('Control+s');
	await expect(page.getByText('Saved', { exact: true })).toBeVisible();
	await expect(page.getByText(`${name} (saved)`, { exact: true }).first()).toBeVisible();
});

test('entering edit mode focuses and selects the Name field, and Control+Enter also saves', async ({
	page
}) => {
	const name = uniqueName('Shortcut autofocus item');
	await createItem(page, { name });
	const editButton = page.getByRole('button', { name: 'Edit', exact: true });
	await expect(editButton).toBeVisible();

	await page.keyboard.press('e');
	const nameInput = page.getByLabel('Name');
	await expect(nameInput).toBeFocused();

	// The field's contents are selected on entry, so typing replaces the name outright.
	await page.keyboard.type(`${name} (via Control+Enter)`);
	await page.keyboard.press('Control+Enter');
	await expect(page.getByText('Saved', { exact: true })).toBeVisible();
	await expect(
		page.getByText(`${name} (via Control+Enter)`, { exact: true }).first()
	).toBeVisible();
});

test('arrow keys move between text cells in a table field, without breaking mid-text cursor movement', async ({
	page
}) => {
	const typeLabel = uniqueName('Shortcut table type');
	await page.goto('/settings/item-types');
	const form = page
		.locator('form')
		.filter({ has: page.getByRole('button', { name: 'Add item type' }) });
	await form.getByLabel('Name').fill(typeLabel);
	await form.getByRole('button', { name: 'Add field', exact: true }).click();
	await form.getByLabel('Field label').last().fill('Cast');
	await form.getByLabel('Field type').last().selectOption('group');
	await form.getByRole('button', { name: 'Add sub-field' }).click();
	await form.getByLabel('Sub-field label').last().fill('Actor');
	await form.getByRole('button', { name: 'Add sub-field' }).click();
	await form.getByLabel('Sub-field label').last().fill('Role');
	await form.getByRole('button', { name: 'Add item type' }).click();
	await expect(page.getByText('Item type created')).toBeVisible();

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Shortcut table item'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByRole('button', { name: 'Add row' }).click();
	await page.getByRole('button', { name: 'Add row' }).click();

	const cell = (row: number, col: number) =>
		page.locator('table tbody tr').nth(row).locator('td').nth(col).locator('input');

	await cell(0, 0).fill('hello');
	await cell(0, 0).press('Home');
	// At the start, ArrowLeft has no cell to move to, so focus stays put.
	await cell(0, 0).press('ArrowLeft');
	await expect(cell(0, 0)).toBeFocused();
	// Mid-text ArrowRight moves the caret, not the cell.
	await cell(0, 0).press('ArrowRight');
	await expect(cell(0, 0)).toBeFocused();

	// At the end of the text, ArrowRight moves to the next cell.
	await cell(0, 0).press('End');
	await cell(0, 0).press('ArrowRight');
	await expect(cell(0, 1)).toBeFocused();

	// ArrowDown always moves a row, whatever the caret position.
	await cell(0, 1).press('ArrowDown');
	await expect(cell(1, 1)).toBeFocused();

	await cell(0, 0).focus();
	await cell(0, 0).press('ArrowDown');
	await expect(cell(1, 0)).toBeFocused();
});

test('Enter submits the edit form from a single-line text field, and the rating widget stays keyboard-operable', async ({
	page
}) => {
	const typeName = uniqueName('Shortcut audit type');
	await createItemType(page, { label: typeName, fields: [{ label: 'Condition', kind: 'rating' }] });

	const itemName = uniqueName('Shortcut audit item');
	await createItem(page, { name: itemName, type: typeName });
	const editButton = page.getByRole('button', { name: 'Edit', exact: true });
	await expect(editButton).toBeVisible();

	await page.keyboard.press('e');
	const nameInput = page.getByLabel('Name');
	await nameInput.fill(`${itemName} (via Enter)`);
	await nameInput.press('Enter');
	await expect(page.getByText('Saved', { exact: true })).toBeVisible();
	await expect(page.getByText(`${itemName} (via Enter)`, { exact: true }).first()).toBeVisible();

	// The rating widget must be keyboard-reachable and operable without a mouse.
	await expect(editButton).toBeVisible();
	await page.keyboard.press('e');
	await page
		.getByRole('radiogroup', { name: 'Condition' })
		.locator('[role="radio"]')
		.first()
		.focus();
	await page.keyboard.press('ArrowRight');
	await expect(page.getByRole('radio', { name: '1 star' })).toHaveAttribute('aria-checked', 'true');
});

test('Escape closes an overlay on top of edit mode without cancelling the edit', async ({
	page
}) => {
	const name = uniqueName('Shortcut overlay item');
	await createItem(page, { name });
	await expect(page.getByRole('button', { name: 'Edit', exact: true })).toBeVisible();

	await page.keyboard.press('e');
	await page.getByLabel('Name').blur();
	await page.keyboard.press('n');
	const capture = page.getByRole('dialog', { name: 'Quick capture' });
	await expect(capture).toBeVisible();

	await page.keyboard.press('Escape');
	await expect(capture).toBeHidden();
	await expect(page.getByLabel('Name')).toBeVisible();
});

test('/ also focuses search from an item page', async ({ page }) => {
	const name = uniqueName('Shortcut slash item');
	await createItem(page, { name });
	await expect(page.getByRole('button', { name: 'Edit', exact: true })).toBeVisible();

	await page.keyboard.press('/');
	await expect(page).toHaveURL(/\/items(\?search=1)?$/);
	await expect(page.getByPlaceholder('Search your items…')).toBeFocused();
});

test('Back returns to the previous page after / navigated to the items list', async ({ page }) => {
	const name = uniqueName('Shortcut back item');
	await createItem(page, { name });
	await page.goto('/settings');
	await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();

	await page.keyboard.press('/');
	const search = page.getByPlaceholder('Search your items…');
	await expect(search).toBeFocused();
	await search.fill(name);
	await page
		.getByRole('link', { name: new RegExp(name) })
		.first()
		.click();
	await expect(page).toHaveURL(/\/items\/(?!new$)[^/]+$/);

	await page.goBack();
	await expect(page).toHaveURL(/\/items$/);
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
});

test('arrow keys move focus between item cards in list view', async ({ page }) => {
	const prefix = uniqueName('Shortcut list nav');
	await createItem(page, { name: `${prefix} A` });
	await createItem(page, { name: `${prefix} B` });

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill(prefix);
	// The search box debounces for 300ms before refetching, which swaps in a
	// fresh (filtered) set of card elements - focus a stale pre-filter card
	// and the debounced refetch drops focus to <body> out from under it, so
	// wait for the filtered count before focusing anything.
	await expect(page.locator('[role="list"] a[href]')).toHaveCount(2);

	const linkA = page.getByRole('link', { name: new RegExp(`${prefix} A`) });
	const linkB = page.getByRole('link', { name: new RegExp(`${prefix} B`) });

	// Creation order (uuid7 ids) puts A above B.
	await linkA.focus();
	await page.keyboard.press('ArrowDown');
	await expect(linkB).toBeFocused();
	await page.keyboard.press('ArrowUp');
	await expect(linkA).toBeFocused();
});

test('arrow keys move focus between item cards in grid view', async ({ page }) => {
	const prefix = uniqueName('Shortcut grid nav');
	await createItem(page, { name: `${prefix} A` });
	await createItem(page, { name: `${prefix} B` });

	await page.goto('/items');
	await page.getByRole('button', { name: 'Grid view' }).click();
	await page.getByPlaceholder('Search your items…').fill(prefix);
	// See the list-view test above: wait for the debounced, filtered set of
	// cards before focusing one, or the refetch drops focus to <body>.
	await expect(page.locator('[data-slot="node-grid"] a[href]')).toHaveCount(2);

	const linkA = page.locator('[data-slot="node-grid"] a', { hasText: `${prefix} A` });
	const linkB = page.locator('[data-slot="node-grid"] a', { hasText: `${prefix} B` });

	// Creation order (uuid7 ids) puts A before B in document order.
	await linkA.focus();
	await page.keyboard.press('ArrowRight');
	await expect(linkB).toBeFocused();
	await page.keyboard.press('ArrowLeft');
	await expect(linkA).toBeFocused();
});
