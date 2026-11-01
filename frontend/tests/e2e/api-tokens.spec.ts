import { E2E_ADMIN, expect, test } from './fixtures';
import type { APIRequestContext, Browser, Page, PlaywrightWorkerArgs } from '@playwright/test';

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
		await dialog.locator('.auth-container:not([hidden]):has(input) button.authorize').click();
		await dialog.getByRole('button', { name: 'Close' }).click();
	}

	const banner = (page: Page) => page.locator('#menagerist-session');
	const SLOW = { timeout: 15_000 };

	/** Logs the entered token out in the bearer block of the Authorize dialog. */
	async function logoutToken(page: Page) {
		await page
			.locator('.swagger-ui .auth-wrapper')
			.getByRole('button', { name: 'Authorize' })
			.click();
		const dialog = page.locator('.dialog-ux');
		await dialog.locator('.auth-container:not([hidden]) button', { hasText: 'Logout' }).click();
		await dialog.getByRole('button', { name: 'Close' }).click();
	}

	/** How many permissions this token holds, asked as a script would (no cookies). */
	async function permissionCount(browser: Browser, baseURL: string | undefined, token: string) {
		const context = await freshContext(browser, baseURL);
		try {
			const res = await context.request.get('/api/v1/auth/me/permissions', {
				headers: { Authorization: `Bearer ${token}` }
			});
			expect(res.status()).toBe(200);
			return ((await res.json()) as { permissions: string[] }).permissions.length;
		} finally {
			await context.close();
		}
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
			const count = await permissionCount(browser, baseURL, token);
			await expect(banner(page)).toHaveText(
				new RegExp(`Using an API token with ${count} permissions?\\.`),
				SLOW
			);
			// The token itself is never written into the page text.
			expect(await banner(page).innerText()).not.toContain(token);
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
			await expect(banner(page)).toContainText('Not signed in. Use Authorize', SLOW);
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

	test('a token that is not accepted is called out, and Logout clears it', async ({
		browser,
		baseURL
	}) => {
		const context = await freshContext(browser, baseURL);
		const page = await context.newPage();
		await page.goto('/api/docs');
		await expect(banner(page)).toContainText('Not signed in', SLOW);

		await authorize(page, 'mnst_not-a-real-token');
		await expect(banner(page)).toContainText(
			'This API token was not accepted (invalid, expired or revoked).',
			SLOW
		);
		await logoutToken(page);
		await expect(banner(page)).toContainText(
			'Not signed in. Use Authorize to sign in or add an API token.',
			SLOW
		);
		await context.close();
	});

	test('a session and a token together say the token takes precedence', async ({
		browser,
		baseURL,
		request
	}) => {
		const created = await request.post('/api/v1/tokens', {
			data: {
				name: `Swagger both ${Date.now()}`,
				password: E2E_ADMIN.password,
				grants: ['graph:type:read']
			}
		});
		expect(created.status()).toBe(201);
		const { id, token } = await created.json();
		try {
			// Its own session, so nothing here ends the worker admin's.
			const context = await freshContext(browser, baseURL);
			const login = await context.request.post('/api/v1/auth/login', {
				data: { username: E2E_ADMIN.username, password: E2E_ADMIN.password }
			});
			expect(login.ok()).toBe(true);
			const page = await context.newPage();
			await page.goto('/api/docs');
			const sessionOnly = `Signed in as ${E2E_ADMIN.displayName} (browser session).`;
			await expect(banner(page)).toContainText(sessionOnly, SLOW);

			await authorize(page, token);
			await expect(banner(page)).toContainText(
				`Signed in as ${E2E_ADMIN.displayName}. An API token is also set and takes precedence for Try it out.`,
				SLOW
			);
			// A good token adds nothing about its validity to this text.
			await expect(banner(page)).not.toContainText('not accepted');
			// The Open Menagerist link and Sign out stay; no Sign in button appears.
			await expect(banner(page).getByRole('button', { name: 'Sign out' })).toBeVisible();
			await expect(banner(page).getByRole('link', { name: 'Sign in' })).toHaveCount(0);

			await logoutToken(page);
			await expect(banner(page)).toContainText(sessionOnly, SLOW);
			await expect(banner(page)).not.toContainText('API token');
			await context.close();
		} finally {
			await request.delete(`/api/v1/tokens/${id}`);
		}
	});
});

test.describe('API tokens card', () => {
	const unique = (label: string) =>
		`${label} ${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

	type TokenRow = { id: string; name: string };

	async function listTokens(request: APIRequestContext): Promise<TokenRow[]> {
		return (await (await request.get('/api/v1/tokens')).json()) as TokenRow[];
	}

	/** Revokes the signed-in admin's tokens whose names start with `prefix`. */
	async function cleanUp(request: APIRequestContext, prefix: string) {
		for (const token of await listTokens(request)) {
			if (token.name.startsWith(prefix)) await request.delete(`/api/v1/tokens/${token.id}`);
		}
	}

	/** A cookie-less API context that sends only the bearer token, as a script would. */
	async function asToken(
		playwright: PlaywrightWorkerArgs['playwright'],
		baseURL: string | undefined,
		token: string
	) {
		return playwright.request.newContext({
			baseURL,
			storageState: { cookies: [], origins: [] },
			extraHTTPHeaders: { Authorization: `Bearer ${token}` }
		});
	}

	function card(page: Page) {
		return page.locator('section[aria-labelledby="tokens-heading"]');
	}

	function row(page: Page, name: string) {
		return page
			.getByRole('table', { name: 'Personal access tokens' })
			.getByRole('row')
			.filter({ hasText: name });
	}

	async function openNewToken(page: Page) {
		await page.getByRole('button', { name: 'New token' }).click();
		const dialog = page.getByRole('dialog', { name: 'New token' });
		await expect(dialog).toBeVisible();
		return dialog;
	}

	/** Fills and submits the New token dialog, leaving the preset as it is unless one is given. */
	async function submitNewToken(
		page: Page,
		name: string,
		options: { password?: string; preset?: 'Read only' | 'Read and write' } = {}
	) {
		const dialog = page.getByRole('dialog', { name: 'New token' });
		await dialog.getByLabel('Name', { exact: true }).fill(name);
		await dialog.getByLabel('Your password').fill(options.password ?? E2E_ADMIN.password);
		if (options.preset) await dialog.getByRole('radio', { name: options.preset }).check();
		await dialog.getByRole('button', { name: 'Create token' }).click();
	}

	async function readSecret(page: Page): Promise<string> {
		const panel = page.getByRole('dialog', { name: 'Your new token' });
		await expect(panel).toBeVisible();
		const value = await panel.getByLabel('Token', { exact: true }).inputValue();
		expect(value).toMatch(/^mnst_/);
		return value;
	}

	async function readSecretAndClose(page: Page): Promise<string> {
		const value = await readSecret(page);
		await page.getByRole('button', { name: 'Done' }).click();
		await expect(page.getByRole('dialog', { name: 'Your new token' })).toBeHidden();
		return value;
	}

	async function createViaApi(request: APIRequestContext, name: string, grants: string[]) {
		const res = await request.post('/api/v1/tokens', {
			data: { name, password: E2E_ADMIN.password, grants }
		});
		expect(res.status()).toBe(201);
		return (await res.json()) as { id: string; token: string };
	}

	test.beforeEach(async ({ page }) => {
		await page.goto('/settings/account');
		await expect(page.getByRole('heading', { name: 'Personal access tokens' })).toBeVisible();
	});

	test('a read only token is created with the password, shown once and can only read', async ({
		page,
		request,
		playwright,
		baseURL
	}) => {
		const name = unique('Read only check');
		try {
			// A wrong password is an inline error and creates nothing.
			const dialog = await openNewToken(page);
			await submitNewToken(page, name, { password: 'definitely-not-the-password' });
			await expect(dialog.getByRole('alert')).toContainText('That password is not right.');
			expect((await listTokens(request)).filter((t) => t.name === name)).toHaveLength(0);

			// The right one shows the one-time panel.
			await dialog.getByLabel('Your password').fill(E2E_ADMIN.password);
			await dialog.getByRole('button', { name: 'Create token' }).click();
			const panel = page.getByRole('dialog', { name: 'Your new token' });
			await expect(panel).toContainText('Copy it now');
			await expect(panel).toContainText('only time');
			const secret = await readSecret(page);

			// The sample command carries the real token and this origin; its request works.
			const sample = await panel.locator('pre code').innerText();
			expect(sample).toContain(secret);
			expect(sample).toContain('Authorization: Bearer');
			expect(sample).toContain(new URL(page.url()).origin);
			// No permission strings or graph terms anywhere in what the card shows.
			const visible = [await card(page).innerText(), await dialog.innerText().catch(() => '')];
			visible.push(await panel.innerText());
			for (const text of visible) {
				expect(text).not.toMatch(/\b(node|edge|graph)s?\b/i);
				expect(text).not.toMatch(/\b[a-z_]+:[a-z_]+:[a-z_]+\b/);
			}

			await page.getByRole('button', { name: 'Done' }).click();
			await expect(panel).toBeHidden();
			await expect(page.locator('body')).not.toContainText(secret);

			// After a reload only the name, grants in words, expiry and last use remain.
			await page.reload();
			const created = row(page, name);
			await expect(created).toHaveCount(1);
			await expect(created).toContainText(/Read .*items/);
			await expect(created).toContainText(/Expires in \d+ days/);
			await expect(created).toContainText('Never used');
			expect(await page.content()).not.toContain(secret);
			const rowText = await created.innerText();
			expect(rowText).not.toMatch(/\b(node|edge|graph)s?\b/i);
			expect(rowText).not.toMatch(/\b[a-z_]+:[a-z_]+:[a-z_]+\b/);

			// The sample command's own request works with the secret.
			const sampled = await asToken(playwright, baseURL, secret);
			try {
				expect((await sampled.get('/api/v1/auth/me/permissions')).status()).toBe(200);
			} finally {
				await sampled.dispose();
			}

			// The secret reads but cannot write.
			const api = await asToken(playwright, baseURL, secret);
			try {
				expect((await api.get('/api/v1/node-type')).status()).toBe(200);
				const write = await api.post('/api/v1/node-type', {
					data: { slug: `ro-${Date.now()}`, label: 'Should not exist' }
				});
				expect(write.status()).toBe(403);
			} finally {
				await api.dispose();
			}

			// Using it shows in the list.
			await page.reload();
			await expect(row(page, name)).toContainText('Used today');
		} finally {
			await cleanUp(request, name);
		}
	});

	test('a read and write token can write', async ({ page, request, playwright, baseURL }) => {
		const name = unique('Read write check');
		const slug = `rw-${Date.now()}`;
		let typeId: string | undefined;
		const api = { current: undefined as APIRequestContext | undefined };
		try {
			await openNewToken(page);
			await submitNewToken(page, name, { preset: 'Read and write' });
			const secret = await readSecretAndClose(page);
			await expect(row(page, name)).toContainText(/read and write/i);

			api.current = await asToken(playwright, baseURL, secret);
			const created = await api.current.post('/api/v1/node-type', {
				data: { slug, label: 'Written by a token' }
			});
			expect(created.status()).toBe(201);
			typeId = ((await created.json()) as { id: string }).id;
		} finally {
			await api.current?.dispose();
			if (typeId) await request.delete(`/api/v1/node-type/${typeId}`);
			await cleanUp(request, name);
		}
	});

	test('the Advanced view grants access area by area', async ({
		page,
		request,
		playwright,
		baseURL
	}) => {
		const name = unique('Advanced check');
		try {
			const dialog = await openNewToken(page);
			await dialog.getByRole('button', { name: 'Advanced' }).click();
			await dialog.getByLabel('Items access', { exact: true }).selectOption({ label: 'Read' });
			await dialog
				.getByLabel('Item types access', { exact: true })
				.selectOption({ label: 'No access' });
			await dialog
				.getByLabel('Collections access', { exact: true })
				.selectOption({ label: 'No access' });
			await dialog.getByLabel('Media access', { exact: true }).selectOption({ label: 'No access' });
			await dialog
				.getByLabel('Presets access', { exact: true })
				.selectOption({ label: 'No access' });
			await dialog
				.getByLabel('Example packs access', { exact: true })
				.selectOption({ label: 'No access' });
			await expect(dialog).toContainText('Custom access');
			await submitNewToken(page, name);
			const secret = await readSecretAndClose(page);
			await expect(row(page, name)).toContainText('Read items');

			const api = await asToken(playwright, baseURL, secret);
			try {
				expect((await api.get('/api/v1/node')).status()).toBe(200);
				expect((await api.get('/api/v1/node-type')).status()).toBe(403);
				expect((await api.get('/api/v1/collection')).status()).toBe(403);
				const write = await api.post('/api/v1/node-type', {
					data: { slug: `adv-${Date.now()}`, label: 'Should not exist' }
				});
				expect(write.status()).toBe(403);
			} finally {
				await api.dispose();
			}
		} finally {
			await cleanUp(request, name);
		}
	});

	test('regenerating keeps the name, retires the old secret and issues a working one', async ({
		page,
		request,
		playwright,
		baseURL
	}) => {
		const name = unique('Regenerate check');
		try {
			const original = await createViaApi(request, name, ['graph:type:read']);
			await page.reload();
			await expect(row(page, name)).toHaveCount(1);

			await page.getByRole('button', { name: `Regenerate ${name}` }).click();
			const dialog = page.getByRole('dialog', { name: 'Regenerate token' });
			await expect(dialog).toBeVisible();
			await dialog.getByLabel('Your password').fill(E2E_ADMIN.password);
			await dialog.getByRole('button', { name: 'Generate new token' }).click();
			const next = await readSecretAndClose(page);
			expect(next).not.toBe(original.token);

			await expect(row(page, name)).toHaveCount(1);
			expect((await listTokens(request)).filter((t) => t.name === name)).toHaveLength(1);

			const oldApi = await asToken(playwright, baseURL, original.token);
			const newApi = await asToken(playwright, baseURL, next);
			try {
				expect((await oldApi.get('/api/v1/node-type')).status()).toBe(401);
				expect((await newApi.get('/api/v1/node-type')).status()).toBe(200);
			} finally {
				await oldApi.dispose();
				await newApi.dispose();
			}
		} finally {
			await cleanUp(request, name);
		}
	});

	test('revoking asks first, stops the token and drops the row without a reload', async ({
		page,
		request,
		playwright,
		baseURL
	}) => {
		const name = unique('Revoke check');
		try {
			const created = await createViaApi(request, name, ['graph:type:read']);
			await page.reload();
			await expect(row(page, name)).toHaveCount(1);

			// Cancelling leaves it alone.
			await page.getByRole('button', { name: `Revoke ${name}` }).click();
			await expect(page.getByText(`Revoke ${name}?`)).toBeVisible();
			await page.getByRole('button', { name: 'Cancel' }).click();
			await expect(row(page, name)).toHaveCount(1);

			await page.getByRole('button', { name: `Revoke ${name}` }).click();
			await page.getByRole('button', { name: 'Revoke token' }).click();
			await expect(page.getByText('Token revoked')).toBeVisible();
			await expect(row(page, name)).toHaveCount(0);

			const api = await asToken(playwright, baseURL, created.token);
			try {
				expect((await api.get('/api/v1/node-type')).status()).toBe(401);
			} finally {
				await api.dispose();
			}
		} finally {
			await cleanUp(request, name);
		}
	});

	test('a token cannot manage tokens', async ({ request, playwright, baseURL }) => {
		const name = unique('Self-service check');
		try {
			const created = await createViaApi(request, name, ['graph:type:read']);
			const api = await asToken(playwright, baseURL, created.token);
			try {
				expect((await api.get('/api/v1/tokens')).status()).toBe(401);
				expect((await api.delete(`/api/v1/tokens/${created.id}`)).status()).toBe(401);
			} finally {
				await api.dispose();
			}
		} finally {
			await cleanUp(request, name);
		}
	});

	test('the New token dialog works from the keyboard alone', async ({ page }) => {
		const newToken = page.getByRole('button', { name: 'New token' });
		await newToken.focus();
		await page.keyboard.press('Enter');
		const dialog = page.getByRole('dialog', { name: 'New token' });
		await expect(dialog).toBeVisible();

		// Focus lands inside the dialog (on its Close button); Tab then walks the controls in reading order.
		const describe = () =>
			page.evaluate(() => {
				const el = document.activeElement as HTMLElement | null;
				if (!el) return '';
				const inDialog = !!el.closest('[role="dialog"]');
				const label =
					el.getAttribute('aria-label') ??
					(el.id ? document.querySelector(`label[for="${el.id}"]`)?.textContent : null) ??
					el.closest('label')?.textContent ??
					el.textContent ??
					'';
				return `${inDialog ? '' : 'OUTSIDE:'}${label.trim()}`;
			});
		const seen: string[] = [await describe()];
		for (let i = 0; i < 10; i++) {
			await page.keyboard.press('Tab');
			seen.push(await describe());
			// Type once focus reaches the Name field (global shortcuts run elsewhere).
			if (seen.at(-1) === 'Name') await page.keyboard.type('Keyboard token');
		}
		expect(seen.some((s) => s.startsWith('OUTSIDE:'))).toBe(false);
		const order = ['Name', 'Your password', 'Read only', 'Advanced', 'Expires after', 'Cancel'];
		let at = 0;
		for (const label of order) {
			const found = seen.findIndex((s, i) => i >= at && s.includes(label));
			expect(found, `"${label}" in ${JSON.stringify(seen)}`).toBeGreaterThanOrEqual(at);
			at = found + 1;
		}

		await page.keyboard.press('Escape');
		await expect(dialog).toBeHidden();
		await expect(newToken).toBeFocused();
	});
});
