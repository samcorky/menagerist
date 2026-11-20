import { test, expect, type APIRequestContext } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * A text field on the item page suggests values used before on the same field of its type. It
 * never offers items to link (#677): that linked an item when clicking from one field to the next.
 */
const { makeItem, makeItemType, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

async function itemWithTwoTextFields(request: APIRequestContext) {
	const type = await makeItemType(request, uniqueName('Shelf box'));
	const res = await request.patch(`/api/v1/node-types/${type.id}`, {
		data: {
			attributes_schema: {
				$schema: 'https://json-schema.org/draft/2020-12/schema',
				type: 'object',
				properties: {
					maker: { type: 'string', title: 'Maker' },
					code: { type: 'string', title: 'Code' }
				}
			}
		}
	});
	expect(res.ok(), await res.text()).toBeTruthy();
	return { item: await makeItem(request, uniqueName('Boxed'), type.slug), type: type.slug };
}

test('clicking from one empty text field to the next links nothing', async ({ page, request }) => {
	const other = await makeItem(request, uniqueName('Bystander'));
	const { item } = await itemWithTwoTextFields(request);

	await page.goto(`/items/${item.id}`);
	await page.getByRole('button', { name: 'Edit', exact: true }).filter({ visible: true }).click();
	await page.getByRole('textbox', { name: 'Maker' }).click();
	await expect(page.getByRole('button', { name: other.name })).toHaveCount(0);
	await page.getByRole('textbox', { name: 'Code' }).click();
	await expect(page.getByRole('textbox', { name: 'Code' })).toBeFocused();
	await expect(page.getByText(`Linked to ${other.name}`)).toHaveCount(0);
});

test('typing suggests values used before, never items to link', async ({ page, request }) => {
	const other = await makeItem(request, uniqueName('Bystander'));
	const { item, type } = await itemWithTwoTextFields(request);
	const maker = uniqueName('Hasbro');
	const sibling = await makeItem(request, uniqueName('Sibling'), type);
	const res = await request.patch(`/api/v1/nodes/${sibling.id}`, {
		data: { attributes: { maker } }
	});
	expect(res.ok(), await res.text()).toBeTruthy();

	await page.goto(`/items/${item.id}`);
	await page.getByRole('button', { name: 'Edit', exact: true }).filter({ visible: true }).click();
	// With suggestions the input is a combobox, so find it by its label.
	const field = page.getByLabel('Maker', { exact: true });
	await field.fill(other.name.slice(0, 12));
	await expect(page.getByRole('button', { name: other.name })).toHaveCount(0);

	// The values come as the browser's own suggestions, which a click elsewhere cannot pick.
	await field.fill(maker.slice(0, 10));
	await expect(field).toHaveAttribute('list', /.+/);
	const list = await field.getAttribute('list');
	await expect(page.locator(`datalist[id="${list}"] option[value="${maker}"]`)).toHaveCount(1);
	await expect(page.locator(`datalist[id="${list}"] option[value="${other.name}"]`)).toHaveCount(0);
	await expect(page.getByText(/^Linked to/)).toHaveCount(0);
});
