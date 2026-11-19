import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** On a phone, Edit must not raise the keyboard by focusing a field. */
const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

test('Edit on a touch screen focuses no field', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Edit focus'));
	await page.goto(`/items/${item.id}`);
	await page.getByRole('button', { name: 'Edit', exact: true }).click();
	await expect(page.getByLabel('Name', { exact: true })).toBeVisible();
	await expect(page.locator('#item-edit-form')).toBeFocused();
	await expect(page.getByLabel('Name', { exact: true })).not.toBeFocused();
});
