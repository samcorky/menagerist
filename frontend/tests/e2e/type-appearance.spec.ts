import { test, expect, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** An item type's icon and colour: chosen in the editor, shown in the list, randomisable. */
const { makeItemType, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const row = (page: Page, text: string) => page.getByRole('listitem').filter({ hasText: text });
const marker = (page: Page, text: string) => row(page, text).locator('[data-slot="type-icon"]');
const preview = (page: Page) =>
	page
		.getByRole('dialog')
		.getByTestId('type-appearance-preview')
		.locator('[data-slot="type-icon"]');

async function openNew(page: Page) {
	await page.goto('/settings/item-types');
	await page.getByRole('button', { name: 'New item type', exact: true }).click();
	return page.getByRole('dialog', { name: 'New item type' });
}

test('a new type gets the icon and colour that were chosen, and keeps them', async ({ page }) => {
	const label = uniqueName('Appearance');
	const dialog = await openNew(page);
	await dialog.getByLabel('Name').fill(label);

	await dialog.getByRole('button', { name: 'Choose icon' }).click();
	await page.getByPlaceholder('Search icons…').fill('movie');
	await page.getByRole('button', { name: 'film', exact: true }).click();
	await dialog.getByRole('radio', { name: 'Red' }).click();
	await expect(preview(page)).toHaveAttribute('data-icon', 'film');
	await expect(preview(page)).toHaveAttribute('data-colour', 'red');

	await dialog.getByRole('button', { name: 'Add item type' }).click();
	await expect(page.getByText('Item type created')).toBeVisible();
	await expect(marker(page, label)).toHaveAttribute('data-icon', 'film');
	await expect(marker(page, label)).toHaveAttribute('data-colour', 'red');

	await page.reload();
	await expect(marker(page, label)).toHaveAttribute('data-icon', 'film');
});

test('searching icons narrows the choices and says when nothing matches', async ({ page }) => {
	const dialog = await openNew(page);
	await dialog.getByRole('button', { name: 'Choose icon' }).click();
	const search = page.getByPlaceholder('Search icons…');

	await search.fill('vinyl');
	await expect(page.getByRole('button', { name: 'disc-3', exact: true })).toBeVisible();
	await expect(page.getByRole('button', { name: 'film', exact: true })).toHaveCount(0);

	await search.fill('zzzzzz');
	await expect(page.getByText('No icons match')).toBeVisible();
});

test('the dice button picks an icon and a colour, and a second press changes them', async ({
	page
}) => {
	const dialog = await openNew(page);
	await expect(preview(page)).toHaveAttribute('data-icon', '');

	await dialog.getByRole('button', { name: 'Randomise icon and colour' }).click();
	const firstIcon = await preview(page).getAttribute('data-icon');
	const firstColour = await preview(page).getAttribute('data-colour');
	expect(firstIcon).not.toBe('');
	expect(firstColour).not.toBe('');

	await dialog.getByRole('button', { name: 'Randomise icon and colour' }).click();
	const secondIcon = await preview(page).getAttribute('data-icon');
	const secondColour = await preview(page).getAttribute('data-colour');
	expect(`${secondIcon}/${secondColour}`).not.toBe(`${firstIcon}/${firstColour}`);
});

test('an existing type can have its icon and colour cleared', async ({ page, request }) => {
	const type = await makeItemType(request, uniqueName('Clearable'));
	await request.patch(`/api/v1/node-type/${type.id}`, { data: { icon: 'music', colour: 'blue' } });
	await page.goto('/settings/item-types');
	await expect(marker(page, type.label)).toHaveAttribute('data-icon', 'music');

	await row(page, type.label).getByRole('button', { name: 'Edit item type' }).click();
	const dialog = page.getByRole('dialog', { name: 'Edit item type' });
	await dialog.getByRole('button', { name: 'Clear icon and colour' }).click();
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(page.getByText('Item type updated')).toBeVisible();

	await expect(marker(page, type.label)).toHaveAttribute('data-icon', '');
});

test('hovering or focusing an icon shows its name', async ({ page }) => {
	const dialog = await openNew(page);
	await dialog.getByRole('button', { name: 'Choose icon' }).click();
	const readout = page.getByTestId('icon-name-readout');

	await page.getByRole('button', { name: 'film', exact: true }).hover();
	await expect(readout).toHaveText('film');
	await page.getByRole('button', { name: 'music', exact: true }).hover();
	await expect(readout).toHaveText('music');
});

test('the icon grid works from the keyboard: type, arrow into it, move, choose', async ({
	page
}) => {
	const dialog = await openNew(page);
	await dialog.getByRole('button', { name: 'Choose icon' }).click();
	await page.getByPlaceholder('Search icons…').fill('movie');
	const results = page.locator('[data-slot="icon-grid"] button');
	const first = await results.nth(0).getAttribute('aria-label');
	const second = await results.nth(1).getAttribute('aria-label');

	await page.keyboard.press('ArrowDown');
	await expect(results.nth(0)).toBeFocused();
	await expect(page.getByTestId('icon-name-readout')).toHaveText(first!);
	await page.keyboard.press('ArrowRight');
	await expect(results.nth(1)).toBeFocused();
	await expect(page.getByTestId('icon-name-readout')).toHaveText(second!);
	await page.keyboard.press('Enter');

	await expect(preview(page)).toHaveAttribute('data-icon', second!);
	await expect(page.getByPlaceholder('Search icons…')).toHaveCount(0);
});

test('ArrowUp from the first row returns to the search box, and Escape closes the grid', async ({
	page
}) => {
	const dialog = await openNew(page);
	await dialog.getByRole('button', { name: 'Choose icon' }).click();
	const search = page.getByPlaceholder('Search icons…');
	await search.fill('movie');
	await page.keyboard.press('ArrowDown');
	await page.keyboard.press('ArrowUp');
	await expect(search).toBeFocused();

	await page.keyboard.press('Escape');
	await expect(search).toHaveCount(0);
	// The editor behind it is still open.
	await expect(dialog).toBeVisible();
});
