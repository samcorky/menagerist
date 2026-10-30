import { test, expect, type Page } from './fixtures';
import { chooseItemType, ownedData, uniqueName } from './helpers';

/** An item's type can be changed or removed after it is set; its values are kept. */
const { makeItem, makeItemType, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const picker = (page: Page) => page.getByRole('combobox', { name: 'Item type' });

const schema = (...keys: string[]) => ({
	$schema: 'https://json-schema.org/draft/2020-12/schema',
	type: 'object',
	properties: Object.fromEntries(keys.map((key) => [key, { type: 'string', title: key }]))
});

async function typeWithFields(
	request: Parameters<typeof makeItemType>[0],
	label: string,
	...keys: string[]
) {
	const type = await makeItemType(request, label);
	const res = await request.patch(`/api/v1/node-type/${type.id}`, {
		data: { attributes_schema: schema(...keys) }
	});
	expect(res.ok(), await res.text()).toBeTruthy();
	return type;
}

async function itemWith(
	request: Parameters<typeof makeItem>[0],
	type: string,
	attributes: Record<string, unknown>
) {
	const item = await makeItem(request, uniqueName('Retyped'), type);
	const res = await request.patch(`/api/v1/node/${item.id}`, { data: { attributes } });
	expect(res.ok(), await res.text()).toBeTruthy();
	return item;
}

const fetchItem = async (request: Parameters<typeof makeItem>[0], id: string) =>
	(await (await request.get(`/api/v1/node/${id}`)).json()) as {
		type: string | null;
		attributes: Record<string, unknown>;
	};

test('changing to a type that has all the fields applies at once, with an undo', async ({
	page,
	request
}) => {
	const from = await typeWithFields(request, uniqueName('From'), 'year');
	const to = await typeWithFields(request, uniqueName('To'), 'year', 'cast');
	const item = await itemWith(request, from.slug, { year: '1979' });

	await page.goto(`/items/${item.id}`);
	await chooseItemType(page, to.label);
	await expect(page.getByText('Item type changed')).toBeVisible();
	expect((await fetchItem(request, item.id)).type).toBe(to.slug);

	await page.getByRole('button', { name: 'Undo' }).click();
	await expect.poll(async () => (await fetchItem(request, item.id)).type).toBe(from.slug);
});

test('values the new type has no field for are listed first, and kept after confirming', async ({
	page,
	request
}) => {
	const from = await typeWithFields(request, uniqueName('From'), 'year', 'runtime');
	const to = await typeWithFields(request, uniqueName('To'), 'year');
	const item = await itemWith(request, from.slug, { year: '1979', runtime: '117' });

	await page.goto(`/items/${item.id}`);
	await chooseItemType(page, to.label);

	const dialog = page.getByRole('dialog', { name: 'Change item type?' });
	await expect(dialog).toContainText('runtime');
	await expect(dialog).toContainText('nothing is deleted');
	expect((await fetchItem(request, item.id)).type).toBe(from.slug);

	await dialog.getByRole('button', { name: 'Change type' }).click();
	await expect.poll(async () => (await fetchItem(request, item.id)).type).toBe(to.slug);
	expect((await fetchItem(request, item.id)).attributes).toEqual({ year: '1979', runtime: '117' });
});

test('cancelling the confirmation leaves the type and the picker as they were', async ({
	page,
	request
}) => {
	const from = await typeWithFields(request, uniqueName('From'), 'runtime');
	const to = await typeWithFields(request, uniqueName('To'), 'year');
	const item = await itemWith(request, from.slug, { runtime: '117' });

	await page.goto(`/items/${item.id}`);
	await chooseItemType(page, to.label);
	await page
		.getByRole('dialog', { name: 'Change item type?' })
		.getByRole('button', { name: 'Cancel' })
		.click();

	await expect(picker(page)).toContainText(from.label);
	expect((await fetchItem(request, item.id)).type).toBe(from.slug);
});

test('the type can be removed, keeping the values', async ({ page, request }) => {
	const from = await typeWithFields(request, uniqueName('From'), 'year');
	const item = await itemWith(request, from.slug, { year: '1979' });

	await page.goto(`/items/${item.id}`);
	await picker(page).click();
	await page.getByRole('option', { name: 'No item type' }).click();
	await page
		.getByRole('dialog', { name: 'Change item type?' })
		.getByRole('button', { name: 'Change type' })
		.click();

	await expect.poll(async () => (await fetchItem(request, item.id)).type).toBeNull();
	expect((await fetchItem(request, item.id)).attributes).toEqual({ year: '1979' });
	await expect(page.getByText('No item type - pick or create one:')).toBeVisible();
});

test('a clash between the item’s own field and the new type’s field is explained, not applied', async ({
	page,
	request
}) => {
	const from = await makeItemType(request, uniqueName('From'));
	const to = await typeWithFields(request, uniqueName('To'), 'year');
	const item = await makeItem(request, uniqueName('Clashing'), from.slug);
	const res = await request.patch(`/api/v1/node/${item.id}`, {
		data: { extra_schema: schema('year') }
	});
	expect(res.ok(), await res.text()).toBeTruthy();

	await page.goto(`/items/${item.id}`);
	await chooseItemType(page, to.label);

	await expect(page.getByText(/already has its own field called/)).toBeVisible();
	expect((await fetchItem(request, item.id)).type).toBe(from.slug);
	await expect(picker(page)).toContainText(from.label);
});
