import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** "Surprise me" opens a random item: any of yours on Home, a collection's own on its page. */
const { makeItem, makeCollection, addToCollection, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

test('Home: opens one of your items', async ({ page, request }) => {
	await makeItem(request, uniqueName('An item'));
	await page.goto('/');
	await page.getByRole('button', { name: 'Surprise me' }).click();
	await expect(page).toHaveURL(/\/items\/(?!new)[0-9a-f-]{36}$/);
});

test('a collection: opens one of its own items, never another', async ({ page, request }) => {
	const inside = await makeItem(request, uniqueName('Inside'));
	await makeItem(request, uniqueName('Outside'));
	const collection = await makeCollection(request, uniqueName('Crate'));
	await addToCollection(request, collection.id, [inside.id]);

	await page.goto(`/collections/${collection.id}`);
	await page.getByRole('button', { name: 'Surprise me' }).click();
	await expect(page).toHaveURL(new RegExp(`/items/${inside.id}$`));
});

test('an empty collection says so instead of navigating', async ({ page, request }) => {
	const collection = await makeCollection(request, uniqueName('Empty crate'));
	await page.goto(`/collections/${collection.id}`);
	await page.getByRole('button', { name: 'Surprise me' }).click();
	await expect(page.getByText('Nothing to pick from yet')).toBeVisible();
	await expect(page).toHaveURL(/\/collections\/empty-crate/);
});
