import type { Locator } from '@playwright/test';
import { test, expect } from './fixtures';
import { openQuickCapture, ownedData, uniqueName } from './helpers';

/** On a phone every place that adds a photo offers both: take one, or choose one already taken. */
const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

async function expectTakeOrChoose(scope: Locator) {
	await expect(scope.getByRole('button', { name: 'Take a photo' })).toBeVisible();
	await expect(scope.getByRole('button', { name: 'Choose a photo' })).toBeVisible();
	// Only the camera input asks the phone for the camera; the other opens the usual picker.
	await expect(scope.locator('input[type="file"][capture]')).toHaveCount(1);
	await expect(scope.locator('input[type="file"]:not([capture])')).toHaveCount(1);
}

test('the item page offers Take a photo and Choose a photo', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Photo choices'));
	await page.goto(`/items/${item.id}`);
	await expectTakeOrChoose(page.getByTestId('cover-placeholder'));
});

test('quick capture offers Take a photo and Choose a photo', async ({ page }) => {
	await page.goto('/');
	await expectTakeOrChoose(await openQuickCapture(page));
});

test('the new item page offers Take a photo and Choose a photo', async ({ page }) => {
	await page.goto('/items/new');
	await expectTakeOrChoose(page.getByRole('group', { name: 'Add cover photo' }));
});
