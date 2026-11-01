import { test, expect, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** An item with no cover shows its type's icon and colour, and a way to add a photo. */
const { makeItem, makeItemType, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

// A 1x1 transparent PNG.
const PNG = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
	'base64'
);

const placeholder = (page: Page) => page.getByTestId('cover-placeholder');
const mark = (page: Page) => placeholder(page).locator('[data-slot="type-icon"]');

test('shows the type icon and colour where the cover would be', async ({ page, request }) => {
	const type = await makeItemType(request, uniqueName('Placeholder type'));
	await request.patch(`/api/v1/node-type/${type.id}`, { data: { icon: 'film', colour: 'red' } });
	const item = await makeItem(request, uniqueName('No cover'), type.slug);
	await page.goto(`/items/${item.id}`);

	await expect(placeholder(page)).toBeVisible();
	await expect(mark(page)).toHaveAttribute('data-icon', 'film');
	await expect(mark(page)).toHaveAttribute('data-colour', 'red');
});

test('an untyped item gets the generic placeholder', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Untyped'));
	await page.goto(`/items/${item.id}`);
	await expect(placeholder(page)).toBeVisible();
	await expect(mark(page)).toHaveAttribute('data-icon', '');
});

test('adding a photo through the placeholder makes it the cover', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Gets a cover'));
	await page.goto(`/items/${item.id}`);
	await placeholder(page)
		.locator('input[type="file"]')
		.setInputFiles({ name: 'front.png', mimeType: 'image/png', buffer: PNG });

	await expect(page.getByTestId('item-cover').locator('img').first()).toBeVisible();
	await expect(placeholder(page)).toHaveCount(0);

	const media = await (await request.get(`/api/v1/media/for-node/${item.id}`)).json();
	expect(media.some((m: { attribute_key?: string }) => m.attribute_key === 'cover')).toBe(true);
});

test('an item with a cover shows no placeholder', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Has cover'));
	await request.post('/api/v1/media/attached', {
		multipart: {
			file: { name: 'a.png', mimeType: 'image/png', buffer: PNG },
			target_type: 'node',
			target_id: item.id,
			attribute_key: 'cover'
		}
	});
	await page.goto(`/items/${item.id}`);
	await expect(page.getByTestId('item-cover').locator('img').first()).toBeVisible();
	await expect(placeholder(page)).toHaveCount(0);
});

test('grid tiles use the type icon and colour for items with no cover', async ({
	page,
	request
}) => {
	const type = await makeItemType(request, uniqueName('Tile type'));
	await request.patch(`/api/v1/node-type/${type.id}`, { data: { icon: 'music', colour: 'blue' } });
	const name = uniqueName('Tile item');
	await makeItem(request, name, type.slug);
	await page.goto('/');
	const tile = page.getByRole('link', { name: new RegExp(name) }).first();
	await expect(tile.locator('[data-slot="type-icon"]')).toHaveAttribute('data-icon', 'music');
	await expect(tile.locator('[data-slot="type-icon"]')).toHaveAttribute('data-colour', 'blue');
});

test('list rows show the type icon and colour, or a small cover when there is one', async ({
	page,
	request
}) => {
	const type = await makeItemType(request, uniqueName('Row type'));
	await request.patch(`/api/v1/node-type/${type.id}`, { data: { icon: 'book', colour: 'green' } });
	const plain = uniqueName('Plain row');
	const covered = uniqueName('Covered row');
	await makeItem(request, plain, type.slug);
	const item = await makeItem(request, covered, type.slug);
	await request.post('/api/v1/media/attached', {
		multipart: {
			file: { name: 'a.png', mimeType: 'image/png', buffer: PNG },
			target_type: 'node',
			target_id: item.id,
			attribute_key: 'cover'
		}
	});

	await page.goto('/');
	await page.getByRole('link', { name: 'Items', exact: true }).first().click();
	const row = (name: string) => page.getByRole('link', { name: new RegExp(name) }).first();

	const mark = row(plain).locator('[data-slot="type-icon"]');
	await expect(mark).toHaveAttribute('data-icon', 'book');
	await expect(mark).toHaveAttribute('data-colour', 'green');
	await expect(row(covered).locator('img')).toBeVisible();
	await expect(row(covered).locator('[data-slot="type-icon"]')).toHaveCount(0);
});
