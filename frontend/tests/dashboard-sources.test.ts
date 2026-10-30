import { beforeEach, describe, expect, it, vi } from 'vitest';

const { searchNodes, countNodeSearches, countNodeTypes, listCollections } = vi.hoisted(() => ({
	searchNodes: vi.fn(),
	countNodeSearches: vi.fn(),
	countNodeTypes: vi.fn(),
	listCollections: vi.fn()
}));
vi.mock('$lib/api/client', () => ({
	searchNodes,
	countNodeSearches,
	countNodeTypes,
	listCollections
}));

import {
	NEWEST_LIMIT,
	EDITED_LIMIT,
	loadCollections,
	loadEdited,
	loadNewest,
	loadStats,
	loadTidy,
	loadTypeBreakdown
} from '$lib/dashboard-sources';
import { favouriteQuery, monthQuery, newestQuery, noPhotoQuery, photoQuery } from '$lib/dashboard';

const page = (items: unknown[]) => ({
	data: { items, total: items.length, total_capped: false, next_cursor: null, warnings: [] }
});
const counted = (counts: Record<string, number>, capped: string[] = []) => ({
	data: {
		counts: Object.fromEntries(
			Object.entries(counts).map(([name, total]) => [
				name,
				{ total, total_capped: capped.includes(name), warnings: [] }
			])
		)
	}
});
const coll = (id: string, kind = 'manual', item_count = 0) => ({ id, name: id, kind, item_count });

beforeEach(() => {
	vi.resetAllMocks();
	searchNodes.mockResolvedValue(page([]));
	countNodeSearches.mockResolvedValue(counted({}));
	countNodeTypes.mockResolvedValue({ data: [] });
	listCollections.mockResolvedValue({ data: [], response: { headers: new Headers() } });
});

describe('newest and edited lists', () => {
	it('asks for the newest items, latest first', async () => {
		searchNodes.mockResolvedValue(page([{ id: 'a' }]));
		const result = await loadNewest();
		expect(result).toEqual({ status: 'ok', data: [{ id: 'a' }] });
		const body = searchNodes.mock.calls[0][0].body;
		expect(body.query).toEqual(newestQuery());
		expect(body.limit).toBe(NEWEST_LIMIT);
	});

	it('asks for the recently edited items by update time', async () => {
		await loadEdited();
		const body = searchNodes.mock.calls[0][0].body;
		expect(body.query.sort).toEqual([{ by: 'updated', dir: 'desc' }]);
		expect(body.limit).toBe(EDITED_LIMIT);
	});

	it('reports an error instead of throwing', async () => {
		searchNodes.mockRejectedValue(new Error('offline'));
		expect(await loadNewest()).toEqual({ status: 'error' });
		expect(await loadEdited()).toEqual({ status: 'error' });
	});
});

describe('loadCollections', () => {
	const withHeaders = (data: unknown[]) => ({ data, response: { headers: new Headers() } });

	it('returns every collection from the shared loader', async () => {
		listCollections.mockResolvedValue(withHeaders([coll('a'), coll('b')]));
		const result = await loadCollections();
		expect(result.status === 'ok' && result.data).toHaveLength(2);
	});

	it('reports an error when the shared loader fails', async () => {
		listCollections.mockResolvedValue({ error: { detail: 'x' } });
		expect(await loadCollections()).toEqual({ status: 'error' });
	});
});

describe('loadStats', () => {
	it('asks for every total in one request and reads exact counts back', async () => {
		countNodeSearches.mockResolvedValue(
			counted({ items: 1284, favourites: 76, month: 18, photo: 1000 }, ['photo'])
		);

		const result = await loadStats();

		expect(countNodeSearches).toHaveBeenCalledTimes(1);
		const queries = countNodeSearches.mock.calls[0][0].body.queries;
		expect(queries.favourites).toEqual(favouriteQuery());
		expect(queries.month).toEqual(monthQuery());
		expect(queries.photo).toEqual(photoQuery());
		expect(result).toEqual({
			status: 'ok',
			data: {
				items: 1284,
				favourites: 76,
				month: { total: 18, capped: false },
				withPhoto: { total: 1000, capped: true }
			}
		});
	});

	it('reports an error when the request fails or leaves a count out', async () => {
		countNodeSearches.mockResolvedValue({ error: { detail: 'x' } });
		expect(await loadStats()).toEqual({ status: 'error' });
		countNodeSearches.mockResolvedValue(counted({ items: 1 }));
		expect(await loadStats()).toEqual({ status: 'error' });
	});
});

describe('loadTypeBreakdown', () => {
	const types = [
		{ slug: 'film', label: 'Film' },
		{ slug: 'book', label: 'Book' }
	];

	it('lists the types in use with their labels, as the server ordered them', async () => {
		countNodeTypes.mockResolvedValue({
			data: [
				{ type: 'film', count: 50 },
				{ type: null, count: 7 },
				{ type: 'gone', count: 2 }
			]
		});

		const result = await loadTypeBreakdown(types as never);

		expect(result).toEqual({
			status: 'ok',
			data: {
				rows: [
					{ slug: 'film', label: 'Film', count: 50 },
					{ slug: 'gone', label: 'gone', count: 2 }
				],
				untyped: 7
			}
		});
	});

	it('has no untyped items when the server lists none', async () => {
		countNodeTypes.mockResolvedValue({ data: [{ type: 'book', count: 1 }] });
		const result = await loadTypeBreakdown(types as never);
		expect(result.status === 'ok' && result.data.untyped).toBe(0);
	});

	it('reports an error when the request fails', async () => {
		countNodeTypes.mockResolvedValue({ error: { detail: 'x' } });
		expect(await loadTypeBreakdown(types as never)).toEqual({ status: 'error' });
	});
});

describe('loadTidy', () => {
	const rows = [
		{ id: 'a', label: 'A', query: noPhotoQuery() },
		{ id: 'b', label: 'B', query: noPhotoQuery() }
	];

	it('counts every row in one request, keyed by row id', async () => {
		countNodeSearches.mockResolvedValue(counted({ a: 232, b: 1000 }, ['b']));

		const result = await loadTidy(rows);

		expect(countNodeSearches).toHaveBeenCalledTimes(1);
		expect(Object.keys(countNodeSearches.mock.calls[0][0].body.queries)).toEqual(['a', 'b']);
		expect(result.map((r) => r.count)).toEqual([
			{ total: 232, capped: false },
			{ total: 1000, capped: true }
		]);
	});

	it('shows no number, but still the rows, when the request fails', async () => {
		countNodeSearches.mockResolvedValue({ error: {} });
		const result = await loadTidy(rows);
		expect(result.map((r) => r.row.id)).toEqual(['a', 'b']);
		expect(result.map((r) => r.count)).toEqual([null, null]);
	});

	it('is empty without calling the server when there are no rows', async () => {
		expect(await loadTidy([])).toEqual([]);
		expect(countNodeSearches).not.toHaveBeenCalled();
	});
});
