import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** The item page holds a loading state until its cover (or the icon in its place) is drawn. */
const { makeItem, makeItemType, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const DELAY_MS = 1500;

// A 1x1 transparent PNG.
const PNG = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
	'base64'
);

const loading = (page: import('@playwright/test').Page) =>
	page.getByTestId('item-cover').getByTestId('cover-loading');

test('keeps the loading state while the item media is fetched, then shows the icon', async ({
	page,
	request
}) => {
	const type = await makeItemType(request, uniqueName('Loading type'));
	await request.patch(`/api/v1/node-types/${type.id}`, { data: { icon: 'film', colour: 'red' } });
	const item = await makeItem(request, uniqueName('No cover yet'), type.slug);
	await page.route('**/api/v1/nodes/*/media', async (route) => {
		await new Promise((resolve) => setTimeout(resolve, DELAY_MS));
		await route.continue();
	});

	await page.goto(`/items/${item.id}`);

	await expect(loading(page)).toBeVisible();
	await expect(page.getByTestId('cover-placeholder')).toHaveCount(0);
	await expect(page.getByTestId('cover-placeholder')).toBeVisible({ timeout: DELAY_MS * 3 });
	await expect(loading(page)).toHaveCount(0);
});

test('keeps the loading state until the cover image has loaded', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Slow picture'));
	await request.post('/api/v1/media/attachments', {
		multipart: {
			file: { name: 'a.png', mimeType: 'image/png', buffer: PNG },
			target_type: 'node',
			target_id: item.id,
			attribute_key: 'cover'
		}
	});
	await page.route(/\/api\/v1\/media\/[^/]+\/(thumbnail|content)$/, async (route) => {
		await new Promise((resolve) => setTimeout(resolve, DELAY_MS));
		await route.continue();
	});

	await page.goto(`/items/${item.id}`);

	// The picture is on its way, so the loading state stays and the image is not shown yet.
	await expect(loading(page)).toBeVisible();
	await expect(page.getByTestId('item-cover').locator('img').first()).toHaveCSS('opacity', '0');
	// Once it has loaded, the loading state goes and the picture shows.
	await expect(loading(page)).toHaveCount(0, { timeout: DELAY_MS * 4 });
	await expect(page.getByTestId('item-cover').locator('img').first()).toHaveCSS('opacity', '1');
});
