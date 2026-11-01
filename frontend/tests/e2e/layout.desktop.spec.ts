import { test, expect } from './fixtures';
import { searchField } from './helpers';

/** The desktop top bar on a 1440p monitor at 125% scaling: full width, compact, icon-led. */
test.use({ viewport: { width: 2048, height: 1152 } });

test.describe('desktop top bar', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/');
		await expect(page.getByRole('button', { name: 'Menu', exact: true })).toBeVisible();
	});

	test('spans the viewport', async ({ page }) => {
		const box = await page.locator('header > div').boundingBox();
		expect(box?.width).toBeGreaterThan(2000);
	});

	test('is compact', async ({ page }) => {
		const box = await page.locator('header').boundingBox();
		expect(box?.height).toBeLessThan(52);
	});

	test('its actions are reachable by name', async ({ page }) => {
		await expect(searchField(page)).toBeVisible();
		await expect(
			page.locator('header').getByRole('button', { name: 'New item', exact: true })
		).toBeVisible();
		await expect(page.getByRole('button', { name: 'Menu', exact: true })).toBeVisible();
	});

	test('shows no visible text on its icons', async ({ page }) => {
		const box = await page.getByRole('button', { name: 'Menu', exact: true }).boundingBox();
		expect(box?.width).toBeLessThan(40);
	});

	test('hovering an icon shows its tooltip', async ({ page }) => {
		await page.getByRole('button', { name: 'Menu', exact: true }).hover();
		await expect(
			page.locator('[data-slot="tooltip-content"]').filter({ hasText: 'Menu' })
		).toBeVisible();
	});

	test('the theme toggle and account button show tooltips', async ({ page }) => {
		await page.getByRole('button', { name: 'Toggle theme', exact: true }).hover();
		await expect(
			page.locator('[data-slot="tooltip-content"]').filter({ hasText: 'Toggle theme' })
		).toBeVisible();
		await page.getByRole('button', { name: /^Account menu for / }).hover();
		await expect(
			page.locator('[data-slot="tooltip-content"]').filter({ hasText: /Account menu for / })
		).toBeVisible();
	});

	test('the account button still opens its menu', async ({ page }) => {
		await page.getByRole('button', { name: /^Account menu for / }).click();
		await expect(page.getByRole('menuitem', { name: 'Sign out' })).toBeVisible();
	});

	test('a modal covers the top bar rather than sitting behind it', async ({ page }) => {
		await page.goto('/settings/item-types');
		await page.getByRole('button', { name: 'New item type', exact: true }).click();
		await expect(page.getByRole('dialog', { name: 'New item type' })).toBeVisible();
		// An open modal makes the page behind it unclickable, so hit-testing cannot show what is
		// painted on top; compare the stacking order the two layers actually have.
		const layers = await page.evaluate(() => {
			const z = (el: Element | null) => (el ? Number(getComputedStyle(el).zIndex) : NaN);
			return {
				bar: z(document.querySelector('header')),
				overlay: z(document.querySelector('[data-slot="responsive-dialog-overlay"]'))
			};
		});
		expect(layers.overlay).toBeGreaterThan(layers.bar);
	});
});
