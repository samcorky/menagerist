import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listCollections } = vi.hoisted(() => ({ listCollections: vi.fn() }));
vi.mock('$lib/api/client', () => ({ listCollections }));

import {
	collectionNameLookup,
	collectionTargets,
	COLLECTIONS_PAGE_SIZE,
	fetchAllCollections
} from '$lib/collections';

const col = (n: number, kind: 'manual' | 'smart' = 'manual') => ({
	id: `id-${n}`,
	name: `Collection ${n}`,
	kind
});
const page = (from: number, count: number, next: boolean) => ({
	data: Array.from({ length: count }, (_, i) => col(from + i)),
	response: new Response(null, { headers: next ? { link: '</x>; rel="next"' } : {} })
});

beforeEach(() => vi.resetAllMocks());

describe('fetchAllCollections', () => {
	it('follows the next link and asks for both kinds', async () => {
		const size = COLLECTIONS_PAGE_SIZE;
		listCollections
			.mockResolvedValueOnce(page(0, size, true))
			.mockResolvedValueOnce(page(size, 2, false));
		const all = await fetchAllCollections();
		expect(all).toHaveLength(size + 2);
		expect(listCollections.mock.calls.map(([o]) => o.query)).toEqual([
			{ after: undefined, limit: size },
			{ after: `id-${size - 1}`, limit: size }
		]);
	});

	it('returns null when any page fails, never a partial list', async () => {
		listCollections
			.mockResolvedValueOnce(page(0, COLLECTIONS_PAGE_SIZE, true))
			.mockResolvedValueOnce({ error: { detail: 'boom' }, response: new Response(null) });
		expect(await fetchAllCollections()).toBeNull();
	});
});

describe('collectionTargets', () => {
	it('lists manual and smart collections, leaving out the one being edited', () => {
		const all = [col(1), col(2, 'smart'), col(3)];
		expect(collectionTargets(all).map((c) => c.id)).toEqual(['id-1', 'id-2', 'id-3']);
		expect(collectionTargets(all, 'id-2').map((c) => c.id)).toEqual(['id-1', 'id-3']);
	});
});

describe('collectionNameLookup', () => {
	it('gives a name, null for a missing one, and undefined while not loaded', () => {
		const lookup = collectionNameLookup([col(1)]);
		expect(lookup('id-1')).toBe('Collection 1');
		expect(lookup('id-9')).toBeNull();
		expect(collectionNameLookup(null)('id-1')).toBeUndefined();
	});
});
