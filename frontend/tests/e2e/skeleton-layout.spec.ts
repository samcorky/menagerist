import { test, expect, type Locator, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * Loading placeholders must sit where the real content lands (design §13a). Each test holds
 * the page's data request, measures the skeleton, releases it, and measures the content.
 */
const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

// A skeleton only appears after the loading delay (300 ms), so hold requests for longer.
const HOLD_MS = 600;
const TOLERANCE = 2;

/** Holds matching GET requests until `release` is called. */
async function hold(page: Page, url: RegExp) {
	let release!: () => void;
	const released = new Promise<void>((resolve) => (release = resolve));
	await page.route(url, async (route) => {
		if (route.request().method() !== 'GET') return route.fallback();
		await released;
		await route.fallback();
	});
	return release;
}

async function measure(locator: Locator) {
	const box = await locator.boundingBox();
	expect(box).not.toBeNull();
	return box!;
}

function expectSameBox(
	skeleton: { x: number; y: number; width: number; height: number },
	content: { x: number; y: number; width: number; height: number },
	dimensions: ('x' | 'y' | 'width' | 'height')[]
) {
	for (const key of dimensions) {
		expect(Math.abs(skeleton[key] - content[key]), `${key}`).toBeLessThanOrEqual(TOLERANCE);
	}
}

test('the item page skeleton holds the cover and details where the content lands', async ({
	page,
	request
}) => {
	const item = await makeItem(request, uniqueName('Skeleton item'));
	await page.setViewportSize({ width: 1400, height: 1000 });
	const release = await hold(page, new RegExp(`/api/v1/nodes/${item.id}$`));

	await page.goto(`/items/${item.id}`);
	const skeleton = page.getByTestId('item-skeleton');
	await expect(skeleton).toBeVisible({ timeout: HOLD_MS * 4 });
	const cover = await measure(skeleton.getByTestId('item-cover'));
	const main = await measure(skeleton.getByTestId('item-main'));

	release();
	await expect(page.getByTestId('item-skeleton')).toHaveCount(0);
	const realCover = await measure(page.getByTestId('item-cover'));
	const realMain = await measure(page.getByTestId('item-main'));

	expectSameBox(cover, realCover, ['x', 'y', 'width']);
	expectSameBox(main, realMain, ['x', 'y', 'width']);
});

for (const view of ['grid', 'list'] as const) {
	test(`the items ${view} skeleton matches the first ${view === 'grid' ? 'card' : 'row'}`, async ({
		page,
		request
	}) => {
		await makeItem(request, uniqueName('Skeleton item'));
		await page.addInitScript((mode) => localStorage.setItem('items-view', mode), view);
		await page.setViewportSize({ width: 1400, height: 1000 });
		const release = await hold(page, /\/api\/v1\/nodes(\?.*)?$/);

		await page.goto('/items');
		const skeleton = page.locator('[data-slot="node-skeleton"]');
		await expect(skeleton).toBeVisible({ timeout: HOLD_MS * 4 });
		const first = await measure(skeleton.locator(':scope > *').first());

		release();
		await expect(skeleton).toHaveCount(0);
		const real = await measure(
			view === 'grid'
				? page.locator('[data-slot="node-grid"] > a').first()
				: page.locator('a[data-slot="item"]').first()
		);

		// A list row's height follows its content (tags, summary), so only the grid card
		// is held to the same height; rows must start in the same place and width.
		expectSameBox(
			first,
			real,
			view === 'grid' ? ['x', 'y', 'width', 'height'] : ['x', 'y', 'width']
		);
	});
}
