import { E2E_ADMIN, expect, test } from './fixtures';
import type { Browser, Page } from '@playwright/test';

// Swagger UI's own assets come from the jsDelivr CDN (the same ones FastAPI uses).
const SWAGGER_ASSET = 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js';

test.describe('personal access tokens in Swagger', () => {
	test.beforeAll(async () => {
		let reachable: boolean;
		try {
			reachable = (await fetch(SWAGGER_ASSET, { signal: AbortSignal.timeout(8000) })).ok;
		} catch {
			reachable = false;
		}
		test.skip(!reachable, 'cdn.jsdelivr.net is unreachable, so Swagger UI cannot load.');
	});

	/** A context with no session, as a script (or a stranger) would have. */
	function freshContext(browser: Browser, baseURL: string | undefined) {
		return browser.newContext({
			baseURL,
			storageState: { cookies: [], origins: [] },
			extraHTTPHeaders: {}
		});
	}

	async function authorize(page: Page, token: string) {
		await page
			.locator('.swagger-ui .auth-wrapper')
			.getByRole('button', { name: 'Authorize' })
			.click();
		const dialog = page.locator('.dialog-ux');
		await dialog.locator('.auth-container:not([hidden]) input[type="text"]').fill(token);
		await dialog.locator('.auth-container:not([hidden]) button.authorize').click();
		await dialog.getByRole('button', { name: 'Close' }).click();
	}

	async function listItemTypes(page: Page) {
		await page.locator('.operation-filter-input').fill('Node Types');
		const block = page.locator('#operations-Node_Types-list_node_types');
		await expect(block).toBeVisible();
		if (!(await block.locator('.opblock-body').isVisible())) {
			await block.locator('.opblock-summary-control').click();
		}
		const tryItOut = block.getByRole('button', { name: 'Try it out' });
		if (await tryItOut.isVisible()) await tryItOut.click();
		await block.getByRole('button', { name: 'Execute' }).click();
		const status = block.locator('.live-responses-table .response .response-col_status').first();
		await expect(status).toBeVisible();
		return { block, status };
	}

	test('a token pasted into Authorize calls the API, and a reload forgets it', async ({
		browser,
		baseURL,
		request
	}) => {
		const created = await request.post('/api/v1/tokens', {
			data: {
				name: `Swagger check ${Date.now()}`,
				password: E2E_ADMIN.password,
				grants: ['graph:type:read']
			}
		});
		expect(created.status()).toBe(201);
		const { id, token } = await created.json();
		try {
			const context = await freshContext(browser, baseURL);
			const page = await context.newPage();
			await page.goto('/api/docs');
			await expect(page.locator('#menagerist-session')).toContainText('Not signed in', {
				timeout: 15_000
			});

			// Without the token the call is refused: there is no session either.
			const refused = await listItemTypes(page);
			await expect(refused.status).toHaveText(/401/);

			await authorize(page, token);
			const accepted = await listItemTypes(page);
			await expect(accepted.status).toHaveText(/200/);
			// Swagger's own curl snippet shows the header it sent.
			await expect(accepted.block.locator('.curl-command').first()).toContainText(
				'Authorization: Bearer mnst_'
			);

			// Logout in the bearer block clears the entered token.
			await page
				.locator('.swagger-ui .auth-wrapper')
				.getByRole('button', { name: 'Authorize' })
				.click();
			const dialog = page.locator('.dialog-ux');
			await dialog.locator('.auth-container:not([hidden]) button', { hasText: 'Logout' }).click();
			await dialog.getByRole('button', { name: 'Close' }).click();
			const loggedOut = await listItemTypes(page);
			await expect(loggedOut.status).toHaveText(/401/);
			await authorize(page, token);
			await expect((await listItemTypes(page)).status).toHaveText(/200/);

			// persistAuthorization is off: nothing stored, and a reload forgets the token.
			const storage = await page.evaluate(() =>
				[...Object.keys(localStorage), ...Object.keys(sessionStorage)].filter(
					(key) => !key.startsWith('sveltekit:')
				)
			);
			expect(storage).toEqual([]);
			await page.reload();
			await expect(page.locator('#menagerist-session')).toContainText('Not signed in', {
				timeout: 15_000
			});
			const forgotten = await listItemTypes(page);
			await expect(forgotten.status).toHaveText(/401/);
			await context.close();
		} finally {
			await request.delete(`/api/v1/tokens/${id}`);
		}
	});
});
