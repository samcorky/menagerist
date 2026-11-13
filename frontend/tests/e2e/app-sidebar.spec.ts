import { expect, request, apiSessionOptions, test, type Page } from './fixtures';
import { asUser, createUserViaApi } from './helpers';

/** The app sidebar: main destinations, grouped sections, rail and drawer states. */
test.use({ viewport: { width: 2048, height: 1152 } });

const sidebar = (page: Page) => page.getByRole('navigation', { name: 'Main', exact: true });
const link = (page: Page, name: string) => sidebar(page).getByRole('link', { name, exact: true });
const burger = (page: Page) => page.getByRole('button', { name: 'Menu', exact: true });

test('shows the main destinations and sections on any signed-in page', async ({ page }) => {
	await page.goto('/items');
	for (const name of [
		'Home',
		'Items',
		'Collections',
		'Explore',
		'Item types',
		'Saved fields',
		'Recently deleted',
		'Account',
		'Status',
		'Settings',
		'API docs'
	]) {
		await expect(link(page, name)).toBeVisible();
	}
});

test('marks the current destination', async ({ page }) => {
	await page.goto('/items');
	await expect(link(page, 'Items')).toHaveAttribute('aria-current', 'page');
	await expect(link(page, 'Home')).not.toHaveAttribute('aria-current', 'page');
});

test('switching sections keeps the sidebar', async ({ page }) => {
	await page.goto('/library/saved-fields');
	await link(page, 'Item types').click();
	await expect(page).toHaveURL(/\/library\/item-types$/);
	await expect(link(page, 'Item types')).toHaveAttribute('aria-current', 'page');
});

test('the burger collapses it to a rail and expands it again', async ({ page }) => {
	await page.goto('/items');
	const wide = await sidebar(page).boundingBox();
	expect(wide?.width).toBeGreaterThan(200);

	await burger(page).click();
	await expect.poll(async () => (await sidebar(page).boundingBox())?.width).toBeLessThan(64);
	await expect(link(page, 'Items')).toBeVisible();

	await burger(page).click();
	await expect.poll(async () => (await sidebar(page).boundingBox())?.width).toBeGreaterThan(200);
});

test('the rail choice survives a reload', async ({ page }) => {
	await page.goto('/items');
	await burger(page).click();
	await expect.poll(async () => (await sidebar(page).boundingBox())?.width).toBeLessThan(64);
	await page.reload();
	await expect(link(page, 'Items')).toBeVisible();
	await expect.poll(async () => (await sidebar(page).boundingBox())?.width).toBeLessThan(64);
	await burger(page).click();
});

test('a rail tooltip names the destination', async ({ page }) => {
	await page.goto('/items');
	await burger(page).click();
	await expect.poll(async () => (await sidebar(page).boundingBox())?.width).toBeLessThan(64);
	await link(page, 'Collections').hover();
	await expect(
		page.locator('[data-slot="tooltip-content"]').filter({ hasText: 'Collections' })
	).toBeVisible();
	await burger(page).click();
});

test('every destination is reachable by keyboard in the rail', async ({ page }) => {
	await page.goto('/');
	await burger(page).click();
	await expect.poll(async () => (await sidebar(page).boundingBox())?.width).toBeLessThan(64);
	await link(page, 'Home').focus();
	await page.keyboard.press('Tab');
	await expect(link(page, 'Items')).toBeFocused();
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(/\/items$/);
	await burger(page).click();
});

test('a section folds away and stays folded after a reload', async ({ page }) => {
	await page.goto('/items');
	await expect(link(page, 'Item types')).toBeVisible();
	await sidebar(page).getByRole('button', { name: 'Library', exact: true }).click();
	await expect(link(page, 'Item types')).toBeHidden();
	await page.reload();
	await expect(link(page, 'Items')).toBeVisible();
	await expect(link(page, 'Item types')).toBeHidden();
	await sidebar(page).getByRole('button', { name: 'Library', exact: true }).click();
	await expect(link(page, 'Item types')).toBeVisible();
});

test('an administrator sees the administration sections', async ({ page }) => {
	await page.goto('/settings/account');
	for (const name of ['Users', 'Devices', 'Backups', 'Scheduled tasks', 'Admin settings']) {
		await expect(link(page, name)).toBeVisible();
	}
});

test('a member does not see administration sections', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const member = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'shell' });
	await adminApi.dispose();

	const { page, context } = await asUser(browser, member);
	await page.setViewportSize({ width: 2048, height: 1152 });
	await page.goto('/settings/account');
	await expect(link(page, 'Account')).toBeVisible();
	await expect(link(page, 'Users')).toHaveCount(0);
	await expect(link(page, 'Backups')).toHaveCount(0);
	await context.close();
});

test('the settings hub still shows its sections beside the sidebar', async ({ page }) => {
	await page.goto('/settings');
	await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();
	await expect(sidebar(page)).toBeVisible();
	await expect(page.locator('main').getByRole('link', { name: /Item types/ })).toBeVisible();
});

test('resizing the window switches between the sidebar and the drawer', async ({ page }) => {
	await page.goto('/items');
	await expect(sidebar(page)).toBeVisible();
	await page.setViewportSize({ width: 600, height: 900 });
	await expect(sidebar(page)).toBeHidden();
	await page.setViewportSize({ width: 1400, height: 900 });
	await expect(sidebar(page)).toBeVisible();
});

test.describe('on a narrow screen', () => {
	test.use({ viewport: { width: 600, height: 900 } });

	test('the burger opens a drawer that closes after choosing a destination', async ({ page }) => {
		await page.goto('/');
		await expect(sidebar(page)).toBeHidden();
		await burger(page).click();
		await expect(sidebar(page)).toBeVisible();
		await link(page, 'Collections').click();
		await expect(page).toHaveURL(/\/collections$/);
		await expect(sidebar(page)).toBeHidden();
	});

	test('keyboard focus stays inside the open drawer and returns to the burger', async ({
		page
	}) => {
		await page.goto('/');
		await burger(page).focus();
		await page.keyboard.press('Enter');
		await expect(sidebar(page)).toBeVisible();
		const inside = () => sidebar(page).evaluate((nav) => nav.contains(document.activeElement));
		for (let i = 0; i < 40; i++) {
			await page.keyboard.press('Tab');
			expect(await inside()).toBe(true);
		}
		for (let i = 0; i < 40; i++) {
			await page.keyboard.press('Shift+Tab');
			expect(await inside()).toBe(true);
		}
		await page.keyboard.press('Escape');
		await expect(sidebar(page)).toBeHidden();
		await expect(burger(page)).toBeFocused();
	});

	test('the drawer is announced as a modal dialog', async ({ page }) => {
		await page.goto('/');
		await burger(page).click();
		await expect(page.getByRole('dialog', { name: 'Menu', exact: true })).toBeVisible();
		await expect(page.getByRole('dialog', { name: 'Menu', exact: true })).toHaveAttribute(
			'aria-modal',
			'true'
		);
	});

	test('Escape closes the drawer', async ({ page }) => {
		await page.goto('/');
		await burger(page).click();
		await expect(sidebar(page)).toBeVisible();
		await page.keyboard.press('Escape');
		await expect(sidebar(page)).toBeHidden();
	});
});

test('there is no sidebar when signed out', async ({ browser, workerBaseURL }) => {
	const context = await browser.newContext({
		baseURL: workerBaseURL,
		storageState: { cookies: [], origins: [] },
		extraHTTPHeaders: {}
	});
	const page = await context.newPage();
	await page.goto('/status');
	await expect(page.getByRole('heading', { name: 'System status' })).toBeVisible();
	await expect(sidebar(page)).toHaveCount(0);
	await expect(burger(page)).toHaveCount(0);
	await context.close();
});

/** The sidebar's own motion: icons stay put, the highlight slides, sections do not drop on load. */
const iconBox = async (page: Page, name: string) =>
	link(page, name).locator('svg').first().boundingBox();

test('the icons stay in the same place when the sidebar becomes a rail and back', async ({
	page
}) => {
	await page.goto('/items');
	const wide = await iconBox(page, 'Items');

	await burger(page).click();
	await expect.poll(async () => (await sidebar(page).boundingBox())?.width).toBeLessThan(64);
	const narrow = await iconBox(page, 'Items');
	expect(narrow?.x).toBe(wide?.x);

	await burger(page).click();
	await expect.poll(async () => (await sidebar(page).boundingBox())?.width).toBeGreaterThan(200);
	expect((await iconBox(page, 'Items'))?.x).toBe(wide?.x);
});

test('the icons stay put through the width change itself', async ({ page }) => {
	await page.goto('/items');
	const start = (await iconBox(page, 'Items'))?.x;
	await burger(page).click();
	const seen = new Set<number | undefined>();
	for (let i = 0; i < 12; i++) {
		seen.add((await iconBox(page, 'Items'))?.x);
		await page.waitForTimeout(20);
	}
	expect([...seen]).toEqual([start]);
});

test('the highlight is one element that moves to the new page', async ({ page }) => {
	await page.goto('/items');
	const highlight = sidebar(page).locator('span[aria-hidden="true"].bg-secondary');
	await expect(highlight).toHaveCount(1);
	// It is placed a moment after the page appears, so wait for it rather than read it at once.
	await expect
		.poll(async () => Math.round((await highlight.boundingBox())?.y ?? 0))
		.toBe(Math.round((await link(page, 'Items').boundingBox())?.y ?? -1));

	await link(page, 'Collections').click();
	await expect(link(page, 'Collections')).toHaveAttribute('aria-current', 'page');
	await expect
		.poll(async () => Math.round((await highlight.boundingBox())?.y ?? 0))
		.toBe(Math.round((await link(page, 'Collections').boundingBox())?.y ?? -1));
});

test('the sidebar is not part of the page fade', async ({ page }) => {
	await page.goto('/items');
	const name = await sidebar(page).evaluate((nav) => getComputedStyle(nav).viewTransitionName);
	expect(name).toBe('app-sidebar');
});

test('sections are already open when the sidebar appears, not dropping down', async ({ page }) => {
	await page.goto('/items');
	await burger(page).click();
	await burger(page).click();
	await expect.poll(async () => (await sidebar(page).boundingBox())?.width).toBeGreaterThan(200);
	const animating = await sidebar(page).evaluate(
		(nav) =>
			nav
				.getAnimations({ subtree: true })
				.filter((a) => (a as CSSAnimation).animationName?.includes('collapsible')).length
	);
	expect(animating).toBe(0);
});

test('the labels fade and the headings fold instead of switching abruptly', async ({ page }) => {
	await page.goto('/items');
	const label = link(page, 'Items').locator('span').first();
	const heading = sidebar(page).getByRole('button', { name: 'Library', exact: true });
	await link(page, 'Items').evaluate((node) => ((node as HTMLElement).dataset.same = 'yes'));

	await burger(page).click();
	await expect.poll(async () => (await sidebar(page).boundingBox())?.width).toBeLessThan(64);
	await expect(label).toHaveCSS('opacity', '0');
	// Folded away and out of reach, not removed.
	await expect.poll(() => heading.evaluate((node) => node.closest('[inert]') !== null)).toBe(true);
	// The same link element survived the change, so its label had something to fade.
	await expect(link(page, 'Items')).toHaveAttribute('data-same', 'yes');

	await burger(page).click();
	await expect(label).toHaveCSS('opacity', '1');
	await expect(heading).toBeVisible();
	expect(await heading.evaluate((node) => node.closest('[inert]') !== null)).toBe(false);
});

/** Back would only repeat the sidebar on its own destinations, so it shows on drill-down pages. */
const back = (page: Page) => page.getByRole('button', { name: 'Back', exact: true });

test('a sidebar destination has no Back button while the sidebar is showing', async ({ page }) => {
	for (const path of ['/library/item-types', '/settings/account', '/library/recently-deleted']) {
		await page.goto(path);
		await expect(sidebar(page)).toBeVisible();
		await expect(back(page)).toHaveCount(0);
	}
});

test('a drill-down page keeps its Back button beside the sidebar', async ({ page }) => {
	await page.goto('/items/new');
	await expect(sidebar(page)).toBeVisible();
	await expect(back(page)).toBeVisible();
});

test('the rail hides Back on a destination too', async ({ page }) => {
	await page.goto('/library/item-types');
	await burger(page).click();
	await expect.poll(async () => (await sidebar(page).boundingBox())?.width).toBeLessThan(64);
	await expect(back(page)).toHaveCount(0);
});
