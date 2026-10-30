import { test, expect, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';
import { setOwnCover } from './examples-helpers';

/** The item page: cover left, details in the middle, a side panel on very wide screens. */
const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

type Request = Parameters<typeof makeItem>[0];

async function open(page: Page, request: Request, width: number, withCover: boolean) {
	const item = await makeItem(request, uniqueName('Layout item'));
	if (withCover) await setOwnCover(request, item.id);
	await page.setViewportSize({ width, height: 1100 });
	await page.goto(`/items/${item.id}`);
	await expect(page.getByTestId('item-main')).toBeVisible();
	if (withCover) await expect(page.getByTestId('item-cover').locator('img').first()).toBeVisible();
	if (!withCover) await expect(page.getByTestId('cover-placeholder')).toBeVisible();
	const box = async (id: string) => (await page.getByTestId(id).boundingBox())!;
	return {
		cover: await box('item-cover'),
		main: await box('item-main'),
		side: await box('item-side')
	};
}

test('three columns on a very wide screen: cover, details, side panel', async ({
	page,
	request
}) => {
	const { cover, main, side } = await open(page, request, 2048, true);
	expect(cover.x + cover.width).toBeLessThanOrEqual(main.x + 1);
	expect(main.x + main.width).toBeLessThanOrEqual(side.x + 1);
	expect(Math.abs(side.y - main.y)).toBeLessThan(8);
});

test('two columns on a laptop: cover left, details with the side panel beneath', async ({
	page,
	request
}) => {
	const { cover, main, side } = await open(page, request, 1200, true);
	expect(cover.x + cover.width).toBeLessThanOrEqual(main.x + 1);
	expect(Math.abs(side.x - main.x)).toBeLessThan(8);
	expect(side.y).toBeGreaterThan(main.y);
});

test('one column on a tablet, cover first', async ({ page, request }) => {
	const { cover, main, side } = await open(page, request, 800, true);
	expect(Math.abs(cover.x - main.x)).toBeLessThan(8);
	expect(main.y).toBeGreaterThanOrEqual(cover.y + cover.height - 1);
	expect(side.y).toBeGreaterThanOrEqual(main.y + main.height - 1);
});

test('the cover column stays in view while the details scroll', async ({ page, request }) => {
	const { cover } = await open(page, request, 1600, true);
	await page.locator('#main-scroll').evaluate((el) => (el.scrollTop = 400));
	const after = (await page.getByTestId('item-cover').boundingBox())!;
	expect(after.y).toBeGreaterThanOrEqual(0);
	expect(after.y).toBeLessThanOrEqual(cover.y + 1);
});

test('without a cover the placeholder holds the cover column, so the layout is the same', async ({
	page,
	request
}) => {
	const { cover, main, side } = await open(page, request, 2048, false);
	expect(cover.x + cover.width).toBeLessThanOrEqual(main.x + 1);
	expect(main.x + main.width).toBeLessThanOrEqual(side.x + 1);
	expect(Math.abs(side.y - main.y)).toBeLessThan(8);
});

test('without a cover, a laptop shows the placeholder left of the details', async ({
	page,
	request
}) => {
	const { cover, main, side } = await open(page, request, 1200, false);
	expect(cover.x + cover.width).toBeLessThanOrEqual(main.x + 1);
	expect(Math.abs(side.x - main.x)).toBeLessThan(8);
	expect(side.y).toBeGreaterThan(main.y);
});
