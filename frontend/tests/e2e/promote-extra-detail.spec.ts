import { test, expect, type APIRequestContext } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * An extra detail several items of a type carry becomes a field of the type for all of them at
 * once (#573), from an item's page or from the item type's editor.
 */
const { makeItem, makeItemType, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const SIGNED = {
	type: 'object',
	properties: {
		signed: { type: 'boolean', title: 'Signed', 'x-menagerist': { kind: 'boolean' } }
	}
};

async function signedItems(request: APIRequestContext, count: number) {
	const type = await makeItemType(request, uniqueName('Poster'));
	const items = [];
	for (let n = 0; n < count; n++) {
		const item = await makeItem(request, uniqueName(`Poster ${n}`), type.slug);
		const res = await request.patch(`/api/v1/nodes/${item.id}`, {
			data: { attributes: { signed: n % 2 === 0 }, extra_schema: SIGNED }
		});
		expect(res.ok(), await res.text()).toBeTruthy();
		items.push(item);
	}
	return { type, items };
}

async function expectPromoted(
	request: APIRequestContext,
	type: { id: string },
	items: { id: string }[]
) {
	const saved = await (await request.get(`/api/v1/node-types/${type.id}`)).json();
	expect(Object.keys(saved.attributes_schema.properties)).toContain('signed');
	for (const [n, item] of items.entries()) {
		const node = await (await request.get(`/api/v1/nodes/${item.id}`)).json();
		expect(node.extra_schema?.properties ?? {}).not.toHaveProperty('signed');
		expect(node.attributes.signed).toBe(n % 2 === 0);
	}
}

test("making an item's extra detail a field moves it off the type's other items too", async ({
	page,
	request
}) => {
	const { type, items } = await signedItems(request, 2);

	await page.goto(`/items/${items[0].id}`);
	await page.getByRole('button', { name: 'Edit', exact: true }).filter({ visible: true }).click();
	await page.getByRole('button', { name: 'Make this a field' }).click();

	const dialog = page.getByRole('dialog', { name: `Make Signed a field of ${type.label}?` });
	await expect(dialog).toContainText('this item and 1 other item');
	await dialog.getByRole('button', { name: 'Make it a field' }).click();
	await expect(page.getByText(`Field added to ${type.label}`)).toBeVisible();

	await expectPromoted(request, type, items);
});

test("the item type's editor lists its items' extra details and adds one to the type", async ({
	page,
	request
}) => {
	const { type, items } = await signedItems(request, 3);

	await page.goto('/library/item-types');
	const row = page.getByRole('listitem').filter({ hasText: type.label });
	await row.getByRole('button', { name: 'Edit item type' }).click();
	const details = page.getByRole('region', { name: 'Extra details on its items' });
	await expect(details).toContainText('on 3 items');
	await details.getByRole('button', { name: `Add Signed to ${type.label}` }).click();

	const dialog = page.getByRole('dialog', { name: `Add Signed to ${type.label}?` });
	await expect(dialog).toContainText('The 3 items that have it now keep their values');
	await dialog.getByRole('button', { name: 'Add field' }).click();
	await expect(page.getByText(`Signed is now a field of ${type.label}`)).toBeVisible();
	await expect(details).toHaveCount(0);

	// Saving the still-open editor keeps the promoted field rather than writing over it.
	await expect(page.getByLabel('Field label')).toHaveValue('Signed');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(page.getByText('Item type updated')).toBeVisible();
	await expectPromoted(request, type, items);
});
