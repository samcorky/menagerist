import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { expect, test, type Page } from '@playwright/test';
import {
	apiSessionOptions,
	COOKIES_BACKEND_PORT,
	COOKIES_STRIPPING_PORT,
	COOKIES_TLS_PORT,
	ensureAdminSession
} from './fixtures';
import { createUserViaApi, type E2EUser } from './helpers';

/**
 * The session cookie in a real browser engine. The app is reached over HTTPS through a TLS proxy
 * (so the cookie is `__Host-Http-menagerist-session`) and directly over plain HTTP (so it keeps
 * the plain name). Runs in Chromium, WebKit and Firefox; each engine signs in as its own user
 * created through the API over plain HTTP, so the three can run at once on one backend.
 */
const PLAIN_URL = `http://localhost:${COOKIES_BACKEND_PORT}`;
const TLS_URL = `https://localhost:${COOKIES_TLS_PORT}`;
const STRIPPING_URL = `https://localhost:${COOKIES_STRIPPING_PORT}`;
const PLAIN = 'menagerist-session';
const PREFIXED = `__Host-Http-${PLAIN}`;
const COLLECTION = '/api/v1/collection';

// Pages are used once their elements appear; the `load` event also waits on fonts and images,
// which stalls Firefox on a busy machine.
const READY = { waitUntil: 'domcontentloaded' } as const;

let user: E2EUser;
let admin: E2EUser;

test.beforeAll(async ({ playwright }, testInfo) => {
	const session = await ensureAdminSession(PLAIN_URL);
	const api = await playwright.request.newContext(apiSessionOptions(PLAIN_URL, session));
	try {
		user = await createUserViaApi(api, PLAIN_URL, { prefix: testInfo.project.name });
		admin = await createUserViaApi(api, PLAIN_URL, {
			prefix: `${testInfo.project.name}-admin`,
			role: 'admin'
		});
	} finally {
		await api.dispose();
	}
});

// Any name: the first test renames the user.
const accountMenu = (page: Page) => page.getByRole('button', { name: /^Account menu for / });

async function signIn(page: Page, origin: string, who: E2EUser = user) {
	await page.goto(`${origin}/login`, READY);
	await page.getByLabel('Username').fill(who.username);
	await page.getByLabel('Password', { exact: true }).fill(who.password);
	await page.getByRole('button', { name: 'Sign in', exact: true }).click();
	await expect(accountMenu(page)).toBeVisible();
}

/** The status of a request made by the page itself, so the browser adds its own headers. */
function fromPage(page: Page, method: string, path: string, body?: object) {
	return page.evaluate(
		async ([m, p, b]) => {
			const res = await fetch(p as string, {
				method: m as string,
				headers: { 'Content-Type': 'application/json' },
				body: b ? (b as string) : undefined
			});
			return res.status;
		},
		[method, path, body ? JSON.stringify(body) : ''] as const
	);
}

const sessionCookies = (page: Page) =>
	page
		.context()
		.cookies()
		.then((all) => all.filter((c) => c.name.endsWith(PLAIN)));

test.describe('over HTTPS', () => {
	test('sign-in sets one prefixed, host-only, strict cookie that scripts cannot see', async ({
		page
	}) => {
		await signIn(page, TLS_URL);

		const cookies = await sessionCookies(page);
		expect(cookies.map((c) => c.name)).toEqual([PREFIXED]);
		expect(cookies[0]).toMatchObject({
			secure: true,
			httpOnly: true,
			path: '/',
			sameSite: 'Strict',
			domain: 'localhost'
		});
		expect(await page.evaluate(() => document.cookie)).not.toContain(PLAIN);

		// The page's own change passes the same-origin check in this engine.
		expect(await fromPage(page, 'PATCH', '/api/v1/auth/me', { display_name: 'Renamed' })).toBe(200);
	});

	// Not every engine stores or sends these names the same way, so the invariant is only that a
	// look-alike carrying the real token is never accepted as the session.
	for (const code of [0x2000, 0x0085, 0x00a0]) {
		const hex = code.toString(16).padStart(4, '0');
		test(`a cookie named with U+${hex} before the real name is no session`, async ({
			page,
			browserName
		}) => {
			await signIn(page, TLS_URL);
			const [real] = await sessionCookies(page);
			await page.context().clearCookies();
			await page.context().addCookies([
				{
					name: `${String.fromCodePoint(code)}${PREFIXED}`,
					value: real.value,
					url: TLS_URL,
					secure: true,
					httpOnly: true,
					sameSite: 'Strict'
				}
			]);

			let status: number;
			try {
				status = await fromPage(page, 'GET', '/api/v1/auth/me');
			} catch (error) {
				// WebKit on Linux sometimes cannot send a control character in a cookie name at
				// all; a name that is never sent cannot be accepted either.
				if (browserName !== 'webkit') throw error;
				test.info().annotations.push({ type: 'note', description: 'WebKit could not send it' });
				return;
			}
			expect(status).toBe(401);
		});
	}

	test('a plain-named cookie is not a session', async ({ page }) => {
		await signIn(page, TLS_URL);
		const [real] = await sessionCookies(page);
		await page.context().clearCookies();
		await page
			.context()
			.addCookies([{ name: PLAIN, value: real.value, url: TLS_URL, httpOnly: true }]);

		expect(await fromPage(page, 'GET', '/api/v1/auth/me')).toBe(401);
	});

	test('page script cannot create the prefixed cookie', async ({ page, browserName }) => {
		test.skip(browserName === 'webkit', 'Safari does not enforce the __Host-Http- prefix');
		await page.goto(`${TLS_URL}/login`, READY);

		await page.evaluate(
			(name) => (document.cookie = `${name}=forged; Secure; Path=/; SameSite=Strict`),
			PREFIXED
		);

		expect(await sessionCookies(page)).toEqual([]);
	});
});

test('over plain HTTP the cookie keeps the plain name', async ({ page }) => {
	await signIn(page, PLAIN_URL);

	const cookies = await sessionCookies(page);
	expect(cookies.map((c) => c.name)).toEqual([PLAIN]);
	expect(cookies[0]).toMatchObject({ secure: false, httpOnly: true, sameSite: 'Strict' });
});

// The status page asks the backend what reached it from this browser.
test.describe('browser check', () => {
	const card = (page: Page) => page.getByTestId('browser-check');

	test('passes over HTTPS through a proxy that keeps the headers', async ({ page }) => {
		await signIn(page, TLS_URL, admin);
		await page.goto(`${TLS_URL}/status`, READY);

		await expect(card(page)).toHaveAttribute('data-state', 'pass');
	});

	test('over plain HTTP the headers still count, with or without Sec-Fetch-Site', async ({
		page
	}) => {
		await signIn(page, PLAIN_URL, admin);
		await page.goto(`${PLAIN_URL}/status`, READY);

		// Engines differ on whether http://localhost counts as secure enough for Sec-Fetch-*.
		await expect(card(page)).toHaveAttribute('data-state', /^(pass|warn)$/);
	});

	test('notices a proxy that removes Origin and Sec-Fetch-Site', async ({ page }) => {
		// Sign-in carries no session cookie yet, so it passes without the headers.
		await signIn(page, STRIPPING_URL, admin);
		await page.goto(`${STRIPPING_URL}/status`, READY);

		await expect(card(page)).toHaveAttribute('data-state', 'stripped');
		await expect(card(page)).toContainText('removing the Origin and Sec-Fetch-Site headers');
	});
});

// A page the browser treats as another site: 127.0.0.1 and localhost never share a site, in any
// engine. (A route-fulfilled page cannot reach loopback, so this is a real local server.)
test.describe('from another site', () => {
	let foreign: Server;
	let FOREIGN = '';

	test.beforeAll(async () => {
		foreign = createServer((_req, res) => {
			res.setHeader('Content-Type', 'text/html');
			res.end(`<!doctype html><title>x</title><a id="go" href="${TLS_URL}/">go</a>`);
		});
		await new Promise<void>((resolve) => foreign.listen(0, '127.0.0.1', resolve));
		FOREIGN = `http://127.0.0.1:${(foreign.address() as AddressInfo).port}`;
	});

	test.afterAll(async () => {
		await new Promise((resolve) => foreign.close(resolve));
	});

	test('a link into the app arrives without the cookie, then is signed in', async ({ page }) => {
		await signIn(page, TLS_URL);
		await page.goto(`${FOREIGN}/`, READY);

		const arrival = page.waitForRequest(
			(r) => r.isNavigationRequest() && r.url() === `${TLS_URL}/`
		);
		await page.locator('#go').click();
		expect(Object.keys(await (await arrival).allHeaders())).not.toContain('cookie');

		await expect(accountMenu(page)).toBeVisible();
	});

	test('a forged form post and fetch change nothing, while the app can', async ({ page }) => {
		await signIn(page, TLS_URL);
		const own = `Own ${Date.now()}`;
		const forged = `Forged ${Date.now()}`;
		expect(await fromPage(page, 'POST', COLLECTION, { name: own })).toBe(201);

		await page.goto(`${FOREIGN}/`, READY);
		const target = `${TLS_URL}${COLLECTION}`;
		// The browser blocks the answer to a credentialed no-cors fetch, so only the end of the
		// request is observable; the listing below shows that nothing changed.
		const settled = Promise.race([
			page.waitForEvent('requestfinished', (r) => r.url() === target),
			page.waitForEvent('requestfailed', (r) => r.url() === target)
		]);
		await page.evaluate(
			([url, name]) => {
				void fetch(url, {
					method: 'POST',
					mode: 'no-cors',
					credentials: 'include',
					headers: { 'Content-Type': 'text/plain' },
					body: JSON.stringify({ name })
				}).catch(() => undefined);
			},
			[target, forged]
		);
		await settled;

		const form = page.waitForResponse(
			(r) =>
				r.url() === target && r.request().method() === 'POST' && r.request().isNavigationRequest()
		);
		await page.evaluate(
			([url, name]) => {
				const f = document.createElement('form');
				f.method = 'POST';
				f.action = url;
				f.enctype = 'text/plain';
				const input = document.createElement('input');
				input.name = `{"name":"${name}","pad":"`;
				input.value = '"}';
				f.appendChild(input);
				document.body.appendChild(f);
				f.submit();
			},
			[target, forged]
		);
		expect([401, 403]).toContain((await form).status());

		// A new page, so the check does not depend on how this engine settles the form's
		// navigation to an error answer.
		const checker = await page.context().newPage();
		await checker.goto(`${TLS_URL}/`, READY);
		const listing = await checker.evaluate(async (url) => (await fetch(url)).text(), COLLECTION);
		expect(listing).toContain(own);
		expect(listing).not.toContain(forged);
	});
});
