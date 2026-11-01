import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** Home groups its items into sections; each folds away and the choice is remembered. */
const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

test('the Recently added section folds away and stays folded after a reload', async ({
	page,
	request
}) => {
	await makeItem(request, uniqueName('Home item'));
	await page.goto('/');
	const toggle = page.locator('main').getByRole('button', { name: /^Newly added/ });
	await expect(toggle).toHaveAttribute('aria-expanded', 'true');
	await toggle.click();
	await expect(toggle).toHaveAttribute('aria-expanded', 'false');
	await page.reload();
	const again = page.locator('main').getByRole('button', { name: /^Newly added/ });
	await expect(again).toHaveAttribute('aria-expanded', 'false');
	await again.click();
	await expect(again).toHaveAttribute('aria-expanded', 'true');
});

test('the Browse all link stays beside the heading when the section is folded', async ({
	page,
	request
}) => {
	await makeItem(request, uniqueName('Home item'));
	await page.goto('/');
	await page
		.locator('main')
		.getByRole('button', { name: /^Newly added/ })
		.click();
	await expect(page.locator('main').getByRole('link', { name: 'Browse all' })).toBeVisible();
	await page
		.locator('main')
		.getByRole('button', { name: /^Newly added/ })
		.click();
});

test('a section title is a heading that contains its toggle, not a heading inside a button', async ({
	page,
	request
}) => {
	await makeItem(request, uniqueName('Heading item'));
	await page.goto('/');
	await expect(page.getByRole('heading', { name: /^Newly added/ })).toBeVisible();

	// Headings inside a button are invalid HTML and drop out of screen readers' heading lists.
	await expect(page.locator('button h2, button h3')).toHaveCount(0);
	await expect(
		page.locator('h2:has(> button[aria-expanded])', { hasText: 'Newly added' })
	).toHaveCount(1);
});
