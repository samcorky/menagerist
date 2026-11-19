import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** The Item types page shows how many items use each type, and Home's tile leads there. */
const { makeItem, makeItemType, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

test('each item type shows how many items use it, linking to those items', async ({
	page,
	request
}) => {
	const busy = await makeItemType(request, uniqueName('Busy type'));
	const idle = await makeItemType(request, uniqueName('Idle type'));
	await makeItem(request, uniqueName('Counted a'), busy.slug);
	await makeItem(request, uniqueName('Counted b'), busy.slug);

	await page.goto('/library/item-types');
	const busyRow = page.getByRole('listitem').filter({ hasText: busy.label });
	await expect(busyRow.getByTestId('type-item-count')).toHaveText('2 items');
	await expect(
		page.getByRole('listitem').filter({ hasText: idle.label }).getByTestId('type-item-count')
	).toHaveText('No items yet');

	await busyRow.getByTestId('type-item-count').click();
	await expect(page).toHaveURL(new RegExp(`/items\\?.*type=${busy.slug}`));
});

test('the Item types tile opens the Item types page', async ({ page, request }) => {
	// An empty library shows a welcome in place of the tiles.
	const type = await makeItemType(request, uniqueName('Tile type'));
	await makeItem(request, uniqueName('Tile item'), type.slug);
	await page.goto('/');
	await page.getByTestId('stat-types').click();
	await expect(page).toHaveURL(/\/library\/item-types$/);
});
