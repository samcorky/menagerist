import { describe, it, expect, vi, beforeEach } from 'vitest';
import '../src/lib/api/client'; // register interceptor side-effects
// noinspection ES6PreferShortImport
import { client } from '../src/lib/api/generated/client.gen';

describe('etag-interceptor (integration-style)', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
	});

	it('caches ETag from 200 and uses If-None-Match -> returns cached body on 304', async () => {
		const etag = '"v1"';
		const lastModified = 'Wed, 21 Oct 2015 07:28:00 GMT';

		let call = 0;

		vi.stubGlobal('fetch', async (request: Request) => {
			call++;
			if (call === 1) {
				return new Response(JSON.stringify({ id: '123', name: 'node1' }), {
					status: 200,
					headers: {
						'Content-Type': 'application/json',
						ETag: etag,
						'Last-Modified': lastModified
					}
				});
			}

			if (call === 2) {
				// ensure the client sent If-None-Match header
				expect(request.headers.get('If-None-Match')).toBe(etag);
				return new Response(null, {
					status: 304,
					headers: {
						ETag: etag,
						'Last-Modified': lastModified
					}
				});
			}

			return new Response(null, { status: 500 });
		});

		const res1 = await client.get({
			url: '/api/node/123',
			responseStyle: 'data',
			throwOnError: true
		});
		expect(res1).toEqual({ id: '123', name: 'node1' });

		const res2 = await client.get({
			url: '/api/node/123',
			responseStyle: 'data',
			throwOnError: true
		});
		expect(res2).toEqual({ id: '123', name: 'node1' });
	});

	it('keys cache by path + query, so different query strings on the same path do not collide', async () => {
		const etag = '"v1"';

		vi.stubGlobal('fetch', async (request: Request) => {
			// Neither request should be treated as a repeat of the other.
			expect(request.headers.get('If-None-Match')).toBeNull();

			const url = new URL(request.url);
			return new Response(JSON.stringify({ type: url.searchParams.get('type') }), {
				status: 200,
				headers: { 'Content-Type': 'application/json', ETag: etag }
			});
		});

		const cats = await client.get({
			url: '/api/nodes?type=cat',
			responseStyle: 'data',
			throwOnError: true
		});
		expect(cats).toEqual({ type: 'cat' });

		const dogs = await client.get({
			url: '/api/nodes?type=dog',
			responseStyle: 'data',
			throwOnError: true
		});
		expect(dogs).toEqual({ type: 'dog' });
	});

	it('reuses the cache when the same path and query string is requested again', async () => {
		const etag = '"v1"';
		let call = 0;

		vi.stubGlobal('fetch', async (request: Request) => {
			call++;
			if (call === 1) {
				return new Response(JSON.stringify({ type: 'cat' }), {
					status: 200,
					headers: { 'Content-Type': 'application/json', ETag: etag }
				});
			}

			expect(request.headers.get('If-None-Match')).toBe(etag);
			return new Response(null, { status: 304, headers: { ETag: etag } });
		});

		const first = await client.get({
			url: '/api/nodes?type=cat',
			responseStyle: 'data',
			throwOnError: true
		});
		expect(first).toEqual({ type: 'cat' });

		const second = await client.get({
			url: '/api/nodes?type=cat',
			responseStyle: 'data',
			throwOnError: true
		});
		expect(second).toEqual({ type: 'cat' });
	});
});
