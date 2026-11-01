import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listNodeTypes } = vi.hoisted(() => ({ listNodeTypes: vi.fn() }));
vi.mock('$lib/api/client', () => ({ listNodeTypes }));

import { fetchAllNodeTypes, NODE_TYPES_PAGE_SIZE } from '$lib/node-types';

const type = (n: number) => ({ id: `id-${n}`, slug: `type-${n}`, label: `Type ${n}` });
const page = (from: number, count: number, next: boolean) => ({
	data: Array.from({ length: count }, (_, i) => type(from + i)),
	response: new Response(null, {
		headers: next ? { link: '</api/v1/node-type?after=x>; rel="next"' } : {}
	})
});

beforeEach(() => vi.resetAllMocks());

describe('fetchAllNodeTypes', () => {
	it('follows the next link until every type is read', async () => {
		const size = NODE_TYPES_PAGE_SIZE;
		listNodeTypes
			.mockResolvedValueOnce(page(0, size, true))
			.mockResolvedValueOnce(page(size, size, true))
			.mockResolvedValueOnce(page(2 * size, 3, false));

		const all = await fetchAllNodeTypes();

		expect(all?.map((t) => t.slug)).toEqual(
			Array.from({ length: 2 * size + 3 }, (_, i) => `type-${i}`)
		);
		expect(listNodeTypes.mock.calls.map(([options]) => options.query)).toEqual([
			{ after: undefined, limit: size },
			{ after: `id-${size - 1}`, limit: size },
			{ after: `id-${2 * size - 1}`, limit: size }
		]);
	});

	it('makes one request when there is no next link', async () => {
		listNodeTypes.mockResolvedValueOnce(page(0, 2, false));
		expect(await fetchAllNodeTypes()).toHaveLength(2);
		expect(listNodeTypes).toHaveBeenCalledTimes(1);
	});

	it('returns null when any page fails, never a partial list', async () => {
		listNodeTypes
			.mockResolvedValueOnce(page(0, NODE_TYPES_PAGE_SIZE, true))
			.mockResolvedValueOnce({ error: { detail: 'boom' }, response: new Response(null) });
		expect(await fetchAllNodeTypes()).toBeNull();
	});
});
