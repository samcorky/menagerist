import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** Bulk selection on a phone (#499): a long press starts it, and the bar clears the bottom bar. */
test.describe.configure({ mode: 'serial' });

const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

test('a long press selects an item and the bar sits above the bottom navigation', async ({
	page,
	request
}) => {
	test.setTimeout(120_000);
	const prefix = uniqueName('Hold').replace(/\W+/g, '');
	for (let i = 1; i <= 3; i++) await makeItem(request, `${prefix} ${i}`);
	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill(prefix);
	const first = page.getByRole('link', { name: new RegExp(`${prefix} 1`) });
	await expect(first).toBeVisible();

	// A held finger: pointer down, hold past 500 ms, lift.
	const touch = { pointerType: 'touch', isPrimary: true, clientX: 40, clientY: 40 };
	await first.dispatchEvent('pointerdown', touch);
	// The hold turns the row into a checkbox, so there is no link left to lift from.

	const bar = page.getByRole('toolbar', { name: 'Actions for selected items' });
	await expect(bar).toBeVisible();
	await expect(bar.getByTestId('selection-count')).toHaveText('1 selected');
	await expect(page).toHaveURL(/\/items$/);
	await expect(page.getByRole('checkbox', { name: `Select ${prefix} 1` })).toBeChecked();

	const nav = await page.locator('nav.md\\:hidden').boundingBox();
	const barBox = await bar.boundingBox();
	expect(nav).not.toBeNull();
	expect(barBox).not.toBeNull();
	expect(barBox!.y + barBox!.height).toBeLessThanOrEqual(nav!.y + 1);
	expect(barBox!.x).toBeGreaterThanOrEqual(0);
	expect(barBox!.x + barBox!.width).toBeLessThanOrEqual(page.viewportSize()!.width);

	if (process.env.SHOTS_DIR) {
		await page.screenshot({ path: `${process.env.SHOTS_DIR}/bulk-phone.png` });
	}

	// The destructive and other actions stay reachable at a finger-sized height.
	for (const name of ['Tag', 'Add to collection', 'Connect', 'Delete']) {
		const button = await bar.getByRole('button', { name }).boundingBox();
		expect(button!.height).toBeGreaterThanOrEqual(44);
	}
});
