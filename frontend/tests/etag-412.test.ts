import { describe, it, expect, vi, beforeEach } from 'vitest';
import '../src/lib/api/client'; // register interceptor
import { client } from '../src/lib/api/generated/client.gen';

describe('etag interceptor - 412 conflict handling', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
	});

	it('sends If-Match on PATCH and clears cache on 412', async () => {
		const etag = '"v1"';
		let call = 0;

		vi.stubGlobal('fetch', async (request: Request) => {
			call++;
			if (call === 1) {
				// initial GET returns resource + etag
				return new Response(JSON.stringify({ id: '123', name: 'node1' }), {
					status: 200,
					headers: { 'Content-Type': 'application/json', ETag: etag }
				});
			}

			if (call === 2) {
				// PATCH should include If-Match header
				expect(request.headers.get('If-Match')).toBe(etag);
				return new Response(JSON.stringify({ detail: 'Precondition failed' }), { status: 412 });
			}

			if (call === 3) {
				// After 412, cache cleared, a subsequent GET should not send If-None-Match
				expect(request.headers.get('If-None-Match')).toBeNull();
				return new Response(JSON.stringify({ id: '123', name: 'node1-updated' }), {
					status: 200,
					headers: { 'Content-Type': 'application/json', ETag: '"v2"' }
				});
			}

			return new Response(null, { status: 500 });
		});

		// initial GET caches ETag
		const res1 = await client.get({
			url: '/api/node/123',
			responseStyle: 'data',
			throwOnError: true
		});
		expect(res1).toEqual({ id: '123', name: 'node1' });

		// attempt PATCH with stale ETag — 412 clears the cache; assert via subsequent GET
		await client.patch({
			url: '/api/node/123',
			body: { name: 'x' },
			responseStyle: 'data'
		});

		const res2 = await client.get({
			url: '/api/node/123',
			responseStyle: 'data',
			throwOnError: true
		});
		expect(res2).toEqual({ id: '123', name: 'node1-updated' });
	});
});
