import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** On a phone there is no hover, so the same toolbar actions keep their text at 44px. */
const { makeCollection, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

test('collection actions keep their labels and 44px height on touch', async ({ page, request }) => {
	const collection = await makeCollection(request, uniqueName('Icons'));
	await page.goto(`/collections/${collection.id}`);
	for (const name of ['Add items', 'Edit', 'Delete']) {
		const button = page.locator('main').getByRole('button', { name, exact: true }).first();
		await expect(button).toBeVisible();
		const box = await button.boundingBox();
		expect(box?.height).toBeGreaterThanOrEqual(44);
		expect(box?.width).toBeGreaterThan(60);
		await expect(button).toContainText(name);
	}
});
