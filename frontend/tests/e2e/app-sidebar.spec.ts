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
	await page.goto('/settings/saved-fields');
	await link(page, 'Item types').click();
	await expect(page).toHaveURL(/\/settings\/item-types$/);
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
