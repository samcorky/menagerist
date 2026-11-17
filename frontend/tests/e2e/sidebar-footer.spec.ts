import { expect, test, type Page } from './fixtures';

/**
 * Settings, API docs and the account menu are pinned to the foot of the sidebar, so they stay in
 * view however many groups are open, in the open sidebar, the rail and the phone drawer.
 */

const SHORT = 420;

const sidebar = (page: Page) => page.locator('#app-sidebar');
const footer = (page: Page) => sidebar(page).getByTestId('sidebar-footer');

/** Open every folded group, so the destinations overflow a short window. */
async function expandEveryGroup(page: Page): Promise<void> {
	// Group headings only: the account menu's button also reports aria-expanded.
	const folded = sidebar(page).locator('p > button[aria-expanded="false"]');
	while ((await folded.count()) > 0) await folded.first().click();
	await expect(page.getByRole('menuitem', { name: 'Sign out' })).toHaveCount(0);
}

async function expectFooterInView(page: Page): Promise<void> {
	const pinned = footer(page);
	await expect(pinned.getByRole('link', { name: 'Settings' })).toBeInViewport();
	await expect(pinned.getByRole('link', { name: 'API docs' })).toBeInViewport();
	await expect(pinned.getByRole('button', { name: /^Account menu for / })).toBeInViewport();
}

test('the open sidebar keeps the footer in view with every group expanded', async ({ page }) => {
	await page.setViewportSize({ width: 1320, height: SHORT });
	await page.goto('/');
	await expandEveryGroup(page);

	// The list really overflows, so the footer would have scrolled away before.
	const list = sidebar(page).locator('div.overflow-y-auto').first();
	expect(await list.evaluate((node) => node.scrollHeight > node.clientHeight)).toBe(true);
	await list.evaluate((node) => node.scrollTo(0, node.scrollHeight));
	await expectFooterInView(page);

	// The name shows beside the picture, and the top bar no longer carries a second menu.
	await expect(footer(page).getByTestId('sidebar-account-name')).toBeVisible();
	await expect(page.getByRole('button', { name: /^Account menu for / })).toHaveCount(1);
});

test('the account menu opens from the footer with the keyboard', async ({ page }) => {
	await page.setViewportSize({ width: 1320, height: SHORT });
	await page.goto('/');
	const account = footer(page).getByRole('button', { name: /^Account menu for / });
	await account.focus();
	await page.keyboard.press('Enter');
	await expect(page.getByRole('menuitem', { name: 'Sign out' })).toBeVisible();
	await expect(page.getByRole('menuitem', { name: 'Account' })).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(account).toBeFocused();
});

test('the rail shows the footer as icons', async ({ page }) => {
	await page.setViewportSize({ width: 1000, height: SHORT });
	await page.goto('/');
	await expandEveryGroup(page);
	await expectFooterInView(page);
	await expect(footer(page).getByTestId('sidebar-account-name')).toHaveCSS('opacity', '0');

	await footer(page)
		.getByRole('button', { name: /^Account menu for / })
		.click();
	await expect(page.getByRole('menuitem', { name: 'Sign out' })).toBeVisible();
});

test('the phone drawer has the footer, and the top bar keeps the account menu', async ({
	page
}) => {
	await page.setViewportSize({ width: 390, height: 560 });
	await page.goto('/');
	const topBarMenu = page.locator('header').getByRole('button', { name: /^Account menu for / });
	await expect(topBarMenu).toBeVisible();

	await page.locator('header').getByRole('button', { name: 'Menu', exact: true }).click();
	await expandEveryGroup(page);
	await expectFooterInView(page);
});
