import { expect, request, apiSessionOptions, test, type Page } from './fixtures';
import { asUser, createUserViaApi } from './helpers';

/** Records every /detail request and every 4xx answer the page causes (the sign-in probe aside). */
function watchNetwork(page: Page) {
	const detailRequests: string[] = [];
	const forbidden: string[] = [];
	page.on('request', (req) => {
		if (req.url().includes('/detail')) detailRequests.push(req.url());
	});
	page.on('response', (res) => {
		if (res.status() === 403) forbidden.push(res.url());
	});
	return { detailRequests, forbidden };
}

async function expectPublicView(page: Page) {
	await expect(page.getByRole('heading', { name: 'System status' })).toBeVisible();
	await expect(page.getByText('All systems operational')).toBeVisible();
	await expect(page.getByText(/Last checked at/)).toBeVisible();
	await expect(page.getByText(/^menagerist v\d/)).toBeVisible();
	await expect(page.getByText('Build info', { exact: true })).toHaveCount(0);
	await expect(page.getByText('Migration', { exact: true })).toHaveCount(0);
	await expect(page.getByText('Commit', { exact: true })).toHaveCount(0);
	await expect(page.getByText('Database', { exact: true })).toHaveCount(0);
}

test('a signed-out visitor sees only the overall state and the version', async ({
	browser,
	workerBaseURL
}) => {
	const context = await browser.newContext({
		baseURL: workerBaseURL,
		storageState: { cookies: [], origins: [] },
		extraHTTPHeaders: {}
	});
	const page = await context.newPage();
	const network = watchNetwork(page);

	await page.goto('/status');
	await expect(page).toHaveURL(/\/status$/);
	await expectPublicView(page);
	await expect(page.getByRole('link', { name: 'Settings' })).toHaveCount(0);
	await expect(page.getByRole('button', { name: /Account menu/ })).toHaveCount(0);

	await page.getByRole('button', { name: 'Refresh status' }).click();
	await expect(page.getByText('All systems operational')).toBeVisible();

	expect(network.detailRequests).toEqual([]);
	expect(network.forbidden).toEqual([]);

	await page.getByRole('link', { name: 'Sign in' }).click();
	await expect(page).toHaveURL(/\/login\?next=%2Fstatus$/);
	await context.close();
});

test('a member sees the public view and causes no forbidden answers', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const member = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'statusmember' });
	await adminApi.dispose();

	const { page, context } = await asUser(browser, member);
	const network = watchNetwork(page);
	await page.goto('/status');
	await expectPublicView(page);

	await page.getByRole('button', { name: 'Refresh status' }).click();
	await expect(page.getByText('All systems operational')).toBeVisible();
	expect(network.detailRequests).toEqual([]);
	expect(network.forbidden).toEqual([]);
	await context.close();
});

test('an administrator also sees the checks and the build info', async ({ page }) => {
	const network = watchNetwork(page);
	await page.goto('/status');

	await expect(page.getByText('All systems operational')).toBeVisible();
	await expect(page.getByText('Build info', { exact: true })).toBeVisible();
	await expect(page.getByText('Database', { exact: true })).toBeVisible();

	// Healthy groups and the build info start collapsed.
	await expect(page.locator('.status-check-detail:visible')).toHaveCount(0);
	await expect(page.getByText('Migration', { exact: true })).toBeHidden();
	const build = page.getByRole('button', { name: 'Show details for build info' });
	await expect(build).toHaveAttribute('aria-expanded', 'false');
	await build.click();
	await expect(page.getByText('Migration', { exact: true })).toBeVisible();
	await expect(page.getByText('Application', { exact: true })).toBeVisible();
	const group = page.getByRole('button', { name: /^Show details for / }).first();
	await group.click();
	await expect(page.locator('.status-check-detail').first()).toBeVisible();
	await expect(page.getByRole('button', { name: /^Hide details for / }).first()).toBeVisible();
	await expect(page.getByRole('link', { name: 'Sign in' })).toHaveCount(0);
	await expect(page.getByRole('link', { name: 'Settings' }).first()).toBeAttached();
	expect(network.detailRequests.length).toBeGreaterThanOrEqual(2);
	expect(network.forbidden).toEqual([]);
});

test('selecting a check highlights it until the page is clicked elsewhere', async ({ page }) => {
	await page.goto('/status');
	await expect(page.getByText('Build info', { exact: true })).toBeVisible();

	// The group is collapsed; selecting its segment opens it.
	await expect(page.locator('.status-check-detail:visible')).toHaveCount(0);
	const segment = page.locator('a[data-status-check-link]').first();
	await expect(segment).toBeVisible();
	const targetId = (await segment.getAttribute('href'))?.slice(1);
	expect(targetId).toBeTruthy();

	await segment.click();

	const detail = page.locator(`#${targetId}`);
	await expect(page).toHaveURL(new RegExp(`#${targetId}$`));
	await expect(detail).toHaveClass(/status-check-highlighted/);
	await expect
		.poll(() => detail.evaluate((element) => element === document.activeElement))
		.toBe(true);

	await page.getByRole('heading', { name: 'System status' }).click();

	await expect(page).toHaveURL(/\/status$/);
	await expect(detail).not.toHaveClass(/status-check-highlighted/);
	await expect
		.poll(() => detail.evaluate((element) => element === document.activeElement))
		.toBe(false);
	await expect(detail).toHaveCSS('outline-style', 'none');
});
