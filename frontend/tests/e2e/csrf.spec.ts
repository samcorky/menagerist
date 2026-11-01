import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { expect, test } from './fixtures';

// A real page on another port of the same host: "same-site", so the SameSite=Strict cookie is
// still sent, and the server's own Sec-Fetch-Site / Origin check is what has to refuse the
// request. (A route-fulfilled page is treated as public and cannot reach loopback at all.)
let foreignServer: Server;
let FOREIGN_ORIGIN = '';

test.beforeAll(async () => {
	foreignServer = createServer((_req, res) => {
		res.setHeader('Content-Type', 'text/html');
		res.end('<!doctype html><title>x</title>');
	});
	await new Promise<void>((resolve) => foreignServer.listen(0, 'localhost', resolve));
	FOREIGN_ORIGIN = `http://localhost:${(foreignServer.address() as AddressInfo).port}`;
});

test.afterAll(async () => {
	await new Promise((resolve) => foreignServer.close(resolve));
});
const COLLECTION = '/api/v1/collection';

test.describe('cross-site mutations', () => {
	test('a page on another origin cannot change anything, while the app can', async ({
		page,
		context,
		request,
		baseURL
	}) => {
		const name = `Forged ${Date.now()}`;
		const own = `Own ${Date.now()}`;

		await page.goto('/');
		const created = await page.evaluate(
			async ([url, collectionName]) => {
				const res = await fetch(url, {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ name: collectionName })
				});
				return res.status;
			},
			[COLLECTION, own]
		);
		expect(created).toBe(201);

		const foreign = await context.newPage();
		await foreign.goto(`${FOREIGN_ORIGIN}/`);

		// A credentialed fetch: the browser sends Sec-Fetch-Site: cross-site and a foreign Origin.
		// The browser blocks the answer (Cross-Origin-Resource-Policy), so only the end of the
		// request is observable here; the listing below shows that nothing changed.
		const target = `${baseURL}${COLLECTION}`;
		const settled = Promise.race([
			foreign.waitForEvent('requestfinished', (r) => r.url() === target),
			foreign.waitForEvent('requestfailed', (r) => r.url() === target)
		]);
		await foreign.evaluate(
			([url, collectionName]) => {
				void fetch(url, {
					method: 'POST',
					mode: 'no-cors',
					credentials: 'include',
					headers: { 'Content-Type': 'text/plain' },
					body: JSON.stringify({ name: collectionName })
				}).catch(() => undefined);
			},
			[target, name]
		);
		await settled;

		// An auto-submitting form is a top-level navigation POST, whose answer is readable.
		const form = foreign.waitForResponse(
			(r) => r.url() === `${baseURL}${COLLECTION}` && r.request().method() === 'POST'
		);
		await foreign.evaluate(
			([url, collectionName]) => {
				const f = document.createElement('form');
				f.method = 'POST';
				f.action = url;
				f.enctype = 'text/plain';
				const input = document.createElement('input');
				input.name = `{"name":"${collectionName}","pad":"`;
				input.value = '"}';
				f.appendChild(input);
				document.body.appendChild(f);
				f.submit();
			},
			[target, name]
		);
		expect((await form).status()).toBe(403);

		const listing = await request.get(COLLECTION);
		const text = await listing.text();
		expect(text).toContain(own);
		expect(text).not.toContain(name);
	});
});
