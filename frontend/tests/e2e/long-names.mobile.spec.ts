import { test, expect, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** Long item names on a very narrow phone: nothing runs off the screen or scrolls sideways. */
const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));
test.use({ viewport: { width: 320, height: 640 } });

const WORDS = `${uniqueName('A very long item name')} ${'with many ordinary words that should wrap '.repeat(5)}`;
const UNBROKEN = `${uniqueName('X')}${'W'.repeat(120)}`;

async function expectNoSidewaysScroll(page: Page, what: string) {
	const widths = await page.evaluate(() => {
		const main = document.getElementById('main-scroll')!;
		return {
			doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
			main: main.scrollWidth - main.clientWidth
		};
	});
	expect(widths, `${what} must not scroll sideways`).toEqual({ doc: 0, main: 0 });
}

for (const [label, name] of [
	['many words', WORDS],
	['one unbroken word', UNBROKEN]
] as const) {
	test(`the item page shows ${label} without overflowing`, async ({ page, request }) => {
		const item = await makeItem(request, name);
		await page.goto(`/items/${item.id}`);
		await expect(page.getByText(name.slice(0, 20)).first()).toBeVisible();
		await expectNoSidewaysScroll(page, 'the item page');
	});

	test(`the list and grid show ${label} without overflowing`, async ({ page, request }) => {
		await makeItem(request, name);
		await page.goto('/items');
		await expect(page.getByRole('link', { name: name.slice(0, 20) }).first()).toBeVisible();
		await expectNoSidewaysScroll(page, 'the list');

		await page.getByRole('button', { name: 'Grid view' }).click();
		await expect(page.getByRole('link', { name: name.slice(0, 20) }).first()).toBeVisible();
		await expectNoSidewaysScroll(page, 'the grid');
	});

	test(`the edit form fits ${label} on screen`, async ({ page, request }) => {
		const item = await makeItem(request, name);
		await page.goto(`/items/${item.id}`);
		await page.getByRole('button', { name: 'Edit', exact: true }).click();
		const field = page.getByLabel('Name', { exact: true }).first();
		await expect(field).toHaveValue(name);
		const box = (await field.boundingBox())!;
		expect(box.x).toBeGreaterThanOrEqual(0);
		expect(box.x + box.width).toBeLessThanOrEqual(320);
		await expectNoSidewaysScroll(page, 'the edit form');
	});
}
