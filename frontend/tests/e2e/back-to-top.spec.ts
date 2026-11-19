import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** A floating Back to top appears on a long page, and focus follows the scroll (#604). */
const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

test('Back to top appears once scrolled down, returns to the top and focuses the heading', async ({
	page,
	request
}) => {
	await makeItem(request, uniqueName('Top item'));
	await page.setViewportSize({ width: 1280, height: 400 });
	await page.goto('/items');
	const button = page.getByTestId('back-to-top');
	await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
	await expect(button).toHaveCount(0);

	await page.evaluate(() => {
		const main = document.getElementById('main-scroll')!;
		const spacer = document.createElement('div');
		spacer.style.height = '3000px';
		main.appendChild(spacer);
		main.scrollTop = main.scrollHeight;
	});
	await expect(button).toBeVisible();
	await button.click();
	await expect
		.poll(() => page.evaluate(() => document.getElementById('main-scroll')!.scrollTop))
		.toBe(0);
	await expect(page.getByRole('heading', { level: 1 })).toBeFocused();
	await expect(button).toHaveCount(0);
});
