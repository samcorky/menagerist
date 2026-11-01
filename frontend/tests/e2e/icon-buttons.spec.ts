import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** Toolbar actions are icon-only on a mouse; their names stay the same for assistive tech. */
const { makeCollection, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const COLLECTION_ACTIONS = ['Add items', 'Edit', 'Delete'];

test('collection actions show only an icon with a mouse', async ({ page, request }) => {
	const collection = await makeCollection(request, uniqueName('Icons'));
	await page.goto(`/collections/${collection.id}`);
	for (const name of COLLECTION_ACTIONS) {
		const button = page.locator('main').getByRole('button', { name, exact: true }).first();
		await expect(button).toBeVisible();
		expect((await button.boundingBox())?.width).toBeLessThan(44);
	}
});

test('the new collection action shows only an icon with a mouse', async ({ page, request }) => {
	await makeCollection(request, uniqueName('Icons'));
	await page.goto('/collections');
	const button = page.locator('main').getByRole('button', { name: 'New collection', exact: true });
	await expect(button.first()).toBeVisible();
	expect((await button.first().boundingBox())?.width).toBeLessThan(44);
});

test('hovering a collection action shows its tooltip', async ({ page, request }) => {
	const collection = await makeCollection(request, uniqueName('Icons'));
	await page.goto(`/collections/${collection.id}`);
	await page.locator('main').getByRole('button', { name: 'Delete', exact: true }).hover();
	await expect(
		page.locator('[data-slot="tooltip-content"]').filter({ hasText: 'Delete' })
	).toBeVisible();
});
