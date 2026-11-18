import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

const { makeItemType, cleanUp } = ownedData();

test.afterEach(async ({ request }) => cleanUp(request));

// Home loads the item type list once and the app keeps it. A type made after that, on another
// page or device, must still be in the picker when it opens, without a reload.
test('the type picker lists a type made after Home loaded the list', async ({ page, request }) => {
	await page.goto('/');
	await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
	const type = await makeItemType(request, uniqueName('Late type'));

	// Navigate inside the app: a reload would clear the cached list and hide the fault.
	await page.getByRole('link', { name: 'Items', exact: true }).first().click();
	await page.getByRole('main').getByRole('button', { name: 'New item' }).click();
	await page.waitForURL(/\/items\/new$/);

	await page.getByRole('combobox', { name: 'Item type' }).click();
	await expect(page.getByRole('option', { name: new RegExp(type.label) })).toBeVisible();
});
