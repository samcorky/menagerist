import { expect, request, sessionOptions, test, type Page } from './fixtures';
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
	await expect(page.getByText('Build info')).toHaveCount(0);
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
	const adminApi = await request.newContext(sessionOptions(workerBaseURL, workerSession));
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
	await expect(page.getByText('Build info')).toBeVisible();
	await expect(page.getByText('Migration', { exact: true })).toBeVisible();
	await expect(page.getByText('Application', { exact: true })).toBeVisible();
	await expect(page.getByText('Database', { exact: true })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Sign in' })).toHaveCount(0);
	await expect(page.getByRole('link', { name: 'Settings' }).first()).toBeAttached();
	expect(network.detailRequests.length).toBeGreaterThanOrEqual(2);
	expect(network.forbidden).toEqual([]);
});
