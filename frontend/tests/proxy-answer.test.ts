import { afterEach, describe, expect, it, vi } from 'vitest';
import { answeredByProxy, proxyAwareFetch } from '../src/lib/proxy-answer';
import { client } from '../src/lib/api/generated/client.gen';
import { offlineController } from '../src/lib/offline.svelte';
import '../src/lib/api/client';

const plain = (status: number, body = '404 page not found') =>
	new Response(body, { status, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
const problem = (status: number) =>
	new Response(JSON.stringify({ type: 'about:blank', title: 'NotFoundError', status }), {
		status,
		headers: { 'Content-Type': 'application/problem+json' }
	});

afterEach(() => {
	vi.unstubAllGlobals();
	offlineController.reportReachable();
});

describe('answeredByProxy', () => {
	it('recognises a proxy standing in for a server that is not there', () => {
		// Traefik while a deployment swaps the container: a bare 404 in plain text.
		expect(answeredByProxy(plain(404))).toBe(true);
		for (const status of [502, 503, 504]) expect(answeredByProxy(plain(status))).toBe(true);
		expect(answeredByProxy(new Response(null, { status: 502 }))).toBe(true);
	});

	it("leaves the app's own answers alone", () => {
		// Every error the app sends is RFC 9457 problem JSON, including a 503 for a lost database.
		expect(answeredByProxy(problem(404))).toBe(false);
		expect(answeredByProxy(problem(503))).toBe(false);
		expect(answeredByProxy(plain(200, 'ok'))).toBe(false);
		expect(answeredByProxy(plain(500))).toBe(false);
		expect(answeredByProxy(plain(400))).toBe(false);
	});
});

describe('proxyAwareFetch', () => {
	it('turns a proxy answer into the error a lost connection gives', async () => {
		vi.stubGlobal('fetch', async () => plain(404));
		await expect(proxyAwareFetch('/api/v1/me')).rejects.toBeInstanceOf(TypeError);
	});

	it('passes the app answers through untouched', async () => {
		const answer = problem(404);
		vi.stubGlobal('fetch', async () => answer);
		expect(await proxyAwareFetch('/api/v1/nodes/x')).toBe(answer);
	});
});

describe('the API client', () => {
	it('reports a proxy 404 as offline, not as something missing', async () => {
		vi.stubGlobal('fetch', async () => plain(404));
		const result = await client.get({ url: '/api/v1/nodes/x' });
		expect(result.response).toBeUndefined();
		expect(offlineController.offline).toBe(true);
	});

	it("still reports the app's own 404 as not found", async () => {
		vi.stubGlobal('fetch', async () => problem(404));
		const result = await client.get({ url: '/api/v1/nodes/x' });
		expect(result.response?.status).toBe(404);
		expect(offlineController.offline).toBe(false);
	});
});
