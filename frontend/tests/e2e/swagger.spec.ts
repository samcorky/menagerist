import { E2E_ADMIN, expect, test } from './fixtures';
import type { Browser, Page } from '@playwright/test';

// Swagger UI's own assets come from the jsDelivr CDN (the same ones FastAPI uses).
const SWAGGER_ASSET = 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js';

test.beforeAll(async () => {
	let reachable: boolean;
	try {
		reachable = (await fetch(SWAGGER_ASSET, { signal: AbortSignal.timeout(8000) })).ok;
	} catch {
		reachable = false;
	}
	test.skip(!reachable, 'cdn.jsdelivr.net is unreachable, so Swagger UI cannot load.');
});

/** Runs one operation through the Swagger UI: expand, Try it out, fill the body, Execute. */
async function execute(page: Page, id: string, body?: object) {
	const tag = id.split('-')[0];
	// Swagger renders tags lazily, so filter the page down to the one we need.
	await page.locator('.operation-filter-input').fill(tag);
	const block = page.locator(`#operations-${id}`);
	await expect(block).toBeVisible();
	if (!(await block.locator('.opblock-body').isVisible())) {
		await block.locator('.opblock-summary-control').click();
	}
	// tryItOutEnabled is on, so the form is normally editable already.
	const tryItOut = block.getByRole('button', { name: 'Try it out' });
	if (await tryItOut.isVisible()) await tryItOut.click();
	if (body) await block.locator('textarea.body-param__text').fill(JSON.stringify(body));
	await block.getByRole('button', { name: 'Execute' }).click();
	const status = block.locator('.live-responses-table .response .response-col_status').first();
	await expect(status).toBeVisible();
	return status;
}

/** A context with no session and none of the fixtures' default headers. */
function freshContext(browser: Browser, baseURL: string | undefined) {
	// Explicit empty storage state and headers, so the worker admin's session
	// (which the fixtures add to every context) is not inherited.
	return browser.newContext({
		baseURL,
		storageState: { cookies: [], origins: [] },
		extraHTTPHeaders: {}
	});
}

const banner = (page: Page) => page.locator('#menagerist-session');
const logo = (page: Page) => page.locator('.swagger-ui .info .menagerist-logo');

// Swagger re-renders and the banner is put back asynchronously, which is slow on a busy machine.
const CHROME = { timeout: 15_000 };

/** The injected banner and logo must survive Swagger's re-renders. */
async function expectChrome(page: Page, text: string) {
	await expect(banner(page)).toContainText(text, CHROME);
	await expect(banner(page)).toHaveCount(1, CHROME);
	await expect(logo(page)).toBeVisible(CHROME);
	await expect(logo(page)).toHaveAttribute('src', '/api/docs/logo.svg', CHROME);
}

test('signs in through the app, uses the API and signs out from the banner', async ({
	browser,
	baseURL
}) => {
	const context = await freshContext(browser, baseURL);
	const page = await context.newPage();
	await page.goto('/api/docs');
	await expectChrome(page, 'Not signed in');
	await expect(page.getByRole('button', { name: 'Authorize' })).toBeHidden();

	// /api/docs is a server route: signing in on the app's page must come back here.
	await banner(page).getByRole('link', { name: 'Sign in' }).click();
	await expect(page).toHaveURL(/\/login\?next=%2Fapi%2Fdocs/);
	await page.getByLabel('Username').fill(E2E_ADMIN.username);
	await page.getByLabel('Password', { exact: true }).fill(E2E_ADMIN.password);
	await page.getByRole('button', { name: 'Sign in', exact: true }).click();
	await expect(page).toHaveURL(/\/api\/docs$/);
	await expectChrome(page, `Signed in as ${E2E_ADMIN.displayName}`);
	await expect(banner(page).getByRole('link', { name: 'Open Menagerist' })).toHaveAttribute(
		'href',
		'/'
	);

	// Interactions re-render Swagger; the banner and logo must stay.
	// Swagger cannot be trusted to keep foreign nodes: remove ours and expect them back.
	await page.evaluate(() =>
		document.querySelectorAll('#menagerist-session, .menagerist-logo').forEach((n) => n.remove())
	);
	await expectChrome(page, 'Signed in as');
	await page.locator('.operation-filter-input').fill('Collections');
	await expectChrome(page, 'Signed in as');
	const created = await execute(page, 'Collections-create_collection', {
		name: `Swagger collection ${Date.now()}`
	});
	await expect(created).toHaveText(/201/);
	await expectChrome(page, 'Signed in as');
	const tag = page.locator('#operations-tag-Collections');
	await tag.click();
	await expectChrome(page, 'Signed in as');
	await tag.click();
	await expectChrome(page, 'Signed in as');
	await page.locator('.operation-filter-input').fill('');
	await expectChrome(page, 'Signed in as');

	await banner(page).getByRole('button', { name: 'Sign out' }).click();
	await expectChrome(page, 'Not signed in');
	await context.close();
});

test('signs in with Try it out and signs out through the API', async ({ browser, baseURL }) => {
	const context = await freshContext(browser, baseURL);
	const page = await context.newPage();
	await page.goto('/api/docs');
	await expectChrome(page, 'Not signed in');

	const login = await execute(page, 'Authentication-sign_in', {
		username: E2E_ADMIN.username,
		password: E2E_ADMIN.password
	});
	await expect(login).toHaveText(/200/);
	await expectChrome(page, `Signed in as ${E2E_ADMIN.displayName}`);

	const logout = await execute(page, 'Authentication-sign_out');
	await expect(logout).toHaveText(/204/);
	await expectChrome(page, 'Not signed in');
	await context.close();
});

/** Filters the page to one tag and expands the operation with this id. */
async function openOperation(page: Page, filter: string, id: string) {
	await page.locator('.operation-filter-input').fill(filter);
	const block = page.locator(`#operations-${id}`);
	await expect(block).toBeVisible();
	if (!(await block.locator('.opblock-body').isVisible())) {
		await block.locator('.opblock-summary-control').click();
	}
	return block;
}

test('shows required permissions and per-operation locks', async ({ browser, baseURL }) => {
	const context = await freshContext(browser, baseURL);
	const page = await context.newPage();
	await page.goto('/api/docs');
	await expectChrome(page, 'Not signed in');
	await expect(page.getByRole('button', { name: 'Authorize' })).toBeHidden();

	const admin = await openOperation(page, 'Node Types', 'Node_Types-delete_node_type');
	await expect(admin.locator('.opblock-description-wrapper')).toContainText('Requires permission');
	await expect(admin.locator('.opblock-description-wrapper')).toContainText(
		'graph:node_type:delete'
	);
	// showExtensions lists the operation extension too.
	await expect(admin).toContainText('x-required-permission');

	const list = await openOperation(page, 'Nodes', 'Nodes-list_nodes');
	await expect(list.locator('.opblock-description-wrapper')).not.toContainText(
		'Requires permission'
	);

	// Protected operations keep a lock that cannot open the Authorize dialog.
	const lock = list.locator('.authorization__btn');
	await expect(lock).toBeVisible();
	await expect(lock).toHaveCSS('pointer-events', 'none');
	await lock.click({ force: true });
	await expect(page.locator('.dialog-ux')).toHaveCount(0);

	// Public operations have no lock.
	const version = await openOperation(page, 'System', 'System-get_version');
	await expect(version.locator('.authorization__btn')).toHaveCount(0);
	await context.close();
});

test('locks follow the real session without changing requests', async ({ browser, baseURL }) => {
	const context = await freshContext(browser, baseURL);
	const page = await context.newPage();
	await page.goto('/api/docs');
	await expectChrome(page, 'Not signed in');

	const list = await openOperation(page, 'Nodes', 'Nodes-list_nodes');
	const lockIcon = list.locator('.authorization__btn svg');
	await expect(lockIcon).toHaveClass('unlocked');

	await banner(page).getByRole('link', { name: 'Sign in' }).click();
	await page.getByLabel('Username').fill(E2E_ADMIN.username);
	await page.getByLabel('Password', { exact: true }).fill(E2E_ADMIN.password);
	await page.getByRole('button', { name: 'Sign in', exact: true }).click();
	await expectChrome(page, 'Signed in as');
	await openOperation(page, 'Nodes', 'Nodes-list_nodes');
	await expect(lockIcon).toHaveClass('locked');

	// The placeholder must not leak: nothing is stored, and Swagger's generated curl carries no
	// cookie. (The browser would silently drop a script-set Cookie header, so the curl snippet
	// is the honest place to look. The Origin header does appear there, on purpose.)
	const created = await execute(page, 'Collections-create_collection', {
		name: `Lock check ${Date.now()}`
	});
	await expect(created).toHaveText(/201/);
	// SvelteKit's own sessionStorage keys (from the app's sign-in page) are not ours.
	const storage = await page.evaluate(() =>
		[...Object.keys(localStorage), ...Object.keys(sessionStorage)].filter(
			(key) => !key.startsWith('sveltekit:')
		)
	);
	expect(storage).toEqual([]);
	const postCurl = await page
		.locator('#operations-Collections-create_collection .curl-command')
		.first()
		.innerText();
	await openOperation(page, 'Nodes', 'Nodes-list_nodes');
	await list.getByRole('button', { name: 'Execute' }).click();
	await expect(
		list.locator('.live-responses-table .response .response-col_status').first()
	).toHaveText(/200/);
	const getCurl = await list.locator('.curl-command').first().innerText();
	// The generated curl carries the server's own origin, which the API requires with a cookie.
	expect(postCurl).toContain(`-H 'Origin: ${new URL(page.url()).origin}'`);
	for (const curl of [postCurl, getCurl]) {
		expect(curl).toContain('curl');
		expect(curl).not.toMatch(/cookie/i);
		expect(curl).not.toMatch(/(^|\s)-b\s/);
		expect(curl).not.toMatch(/session/i);
	}

	await banner(page).getByRole('button', { name: 'Sign out' }).click();
	await expectChrome(page, 'Not signed in');
	await openOperation(page, 'Nodes', 'Nodes-list_nodes');
	await expect(lockIcon).toHaveClass('unlocked');
	await context.close();
});
