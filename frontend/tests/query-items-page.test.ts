import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { listNodes, searchNodes } = vi.hoisted(() => ({
	listNodes: vi.fn(),
	searchNodes: vi.fn()
}));
vi.mock('$lib/api/client', () => ({ listNodes, searchNodes }));

import { encodeQuery } from '$lib/query/codec';
import {
	combinePrefix,
	createFilterWriter,
	filterToken,
	formatTotal,
	loadItemsPage,
	readFilter,
	searchTextIgnored,
	totalLine,
	usesSearch,
	withFilter
} from '$lib/query/items-page';
import { emptyQuery, removeAt } from '$lib/query/tree';
import type { Condition, Query } from '$lib/query/types';

const favourite: Query = {
	v: 1,
	where: { op: 'and', children: [{ kind: 'favourite', value: true }] },
	sort: []
};
const respond = (status: number, link = '') =>
	({ status, headers: new Headers(link ? { link } : {}) }) as Response;
const searchResult = (data: Record<string, unknown>) => ({
	data: { items: [], total: 0, total_capped: false, warnings: [], ...data },
	response: respond(200)
});

beforeEach(() => vi.resetAllMocks());

describe('loadItemsPage', () => {
	it('uses the item list when the filter has no conditions', async () => {
		listNodes.mockResolvedValue({
			data: [{ id: 'a' }],
			response: respond(200, '</node?after=a>; rel="next"')
		});
		const page = await loadItemsPage({
			filter: emptyQuery(),
			basics: { type: 'film', q: 'alien' },
			after: 'z'
		});
		expect(listNodes).toHaveBeenCalledWith({
			query: { after: 'z', limit: 50, type: 'film', q: 'alien' }
		});
		expect(searchNodes).not.toHaveBeenCalled();
		expect(page).toMatchObject({ status: 'ok', items: [{ id: 'a' }], hasMore: true, total: null });
	});

	it('searches with the page filters folded in when there are conditions', async () => {
		searchNodes.mockResolvedValue(
			searchResult({ items: [{ id: 'b' }], total: 1, next_cursor: 'c2' })
		);
		const page = await loadItemsPage({
			filter: favourite,
			basics: { type: 'film', q: 'alien' },
			cursor: 'c1'
		});
		expect(listNodes).not.toHaveBeenCalled();
		expect(searchNodes).toHaveBeenCalledWith({
			body: {
				query: {
					v: 1,
					where: {
						op: 'and',
						children: [
							{ kind: 'favourite', value: true },
							{ kind: 'type', in: ['film'] },
							{ kind: 'text', q: 'alien' }
						]
					},
					sort: []
				},
				limit: 50,
				cursor: 'c1'
			}
		});
		expect(page).toMatchObject({ status: 'ok', hasMore: true, cursor: 'c2', total: 1 });
	});

	it('treats a sort on its own as a search', async () => {
		searchNodes.mockResolvedValue(searchResult({}));
		await loadItemsPage({
			filter: { v: 1, where: null, sort: [{ by: 'name', dir: 'asc' }] },
			basics: { type: null, q: '' }
		});
		expect(searchNodes).toHaveBeenCalled();
	});

	it('reports a capped total', async () => {
		searchNodes.mockResolvedValue(searchResult({ total: 1000, total_capped: true }));
		const page = await loadItemsPage({ filter: favourite, basics: { type: null, q: '' } });
		expect(page.status === 'ok' && formatTotal(page.total ?? 0, page.totalCapped)).toBe(
			'1,000+ items'
		);
	});

	it('returns the server detail for a refused filter', async () => {
		searchNodes.mockResolvedValue({
			error: { detail: 'where.children[0]: That value does not fit a number field.' },
			response: respond(400)
		});
		expect(await loadItemsPage({ filter: favourite, basics: { type: null, q: '' } })).toEqual({
			status: 'rejected',
			detail: 'where.children[0]: That value does not fit a number field.'
		});
	});

	it('does not send a filter that the page filters push over the limit', async () => {
		const full: Query = {
			v: 1,
			where: {
				op: 'and',
				children: Array.from({ length: 50 }, (): Condition => ({ kind: 'favourite', value: true }))
			},
			sort: []
		};
		expect(await loadItemsPage({ filter: full, basics: { type: 'film', q: '' } })).toEqual({
			status: 'too-many'
		});
		expect(searchNodes).not.toHaveBeenCalled();
	});

	it('reports other failures for a toast', async () => {
		searchNodes.mockResolvedValue({ error: {}, response: respond(500) });
		expect(await loadItemsPage({ filter: favourite, basics: { type: null, q: '' } })).toMatchObject(
			{ status: 'failed', title: 'Something went wrong' }
		);
	});
});

describe('URL state', () => {
	it('reads a valid filter and flags a broken one', () => {
		expect(readFilter(encodeQuery(favourite))).toEqual({ query: favourite, invalid: false });
		expect(readFilter('not-a-filter')).toEqual({ query: emptyQuery(), invalid: true });
		expect(readFilter(null)).toEqual({ query: emptyQuery(), invalid: false });
	});

	it('removes the parameter when the filter is empty and keeps other parameters', () => {
		const params = new URLSearchParams({ type: 'film', f: encodeQuery(favourite) });
		expect(withFilter(params, emptyQuery()).toString()).toBe('type=film');
		expect(withFilter(new URLSearchParams(), favourite).get('f')).toBe(encodeQuery(favourite));
		expect(filterToken({ v: 1, where: null, sort: [{ by: 'name' }] })).not.toBeNull();
	});

	it('uses the search endpoint only with conditions or a sort', () => {
		expect(usesSearch(emptyQuery())).toBe(false);
		expect(usesSearch(favourite)).toBe(true);
		expect(usesSearch({ v: 1, where: null, sort: [{ by: 'created' }] })).toBe(true);
	});

	it('formats totals', () => {
		expect(formatTotal(1, false)).toBe('1 item');
		expect(formatTotal(12345, false)).toBe('12,345 items');
		expect(formatTotal(1000, true)).toBe('1,000+ items');
	});

	it('knows where the filter sits in the combined tree', () => {
		const any: Query = { ...favourite, where: { ...favourite.where!, op: 'or' } };
		expect(combinePrefix(any, { type: 'film', q: '' })).toEqual([0]);
		expect(combinePrefix(any, { type: null, q: '' })).toEqual([]);
		expect(combinePrefix(favourite, { type: 'film', q: 'x' })).toEqual([]);
	});
});

describe('createFilterWriter', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => vi.useRealTimers());

	it('debounces typing, pushes once per session and replaces after', () => {
		const navigate = vi.fn();
		const writer = createFilterWriter(navigate, 250);
		writer.startSession();
		writer.write(favourite, { debounce: true });
		writer.write(emptyQuery(), { debounce: true });
		expect(navigate).not.toHaveBeenCalled();
		vi.advanceTimersByTime(250);
		expect(navigate).toHaveBeenCalledTimes(1);
		expect(navigate).toHaveBeenLastCalledWith(emptyQuery(), false);
		writer.write(favourite);
		expect(navigate).toHaveBeenLastCalledWith(favourite, true);
	});

	it('cancels a pending write', () => {
		const navigate = vi.fn();
		const writer = createFilterWriter(navigate, 250);
		writer.write(favourite, { debounce: true });
		writer.cancel();
		vi.advanceTimersByTime(500);
		expect(navigate).not.toHaveBeenCalled();
	});
});

describe('review fixes', () => {
	const any: Query = { ...favourite, where: { ...favourite.where!, op: 'or' } };
	const long = 'x'.repeat(201);

	it('maps paths with the same inclusion rule as combine', () => {
		expect(combinePrefix(any, { type: null, q: long })).toEqual([]);
		expect(combinePrefix(any, { type: null, q: 'x'.repeat(200) })).toEqual([0]);
	});

	it('says when the search text is too long for a filtered search', () => {
		expect(searchTextIgnored(favourite, long)).toBe(true);
		expect(searchTextIgnored(favourite, 'alien')).toBe(false);
		expect(searchTextIgnored(emptyQuery(), long)).toBe(false);
	});

	it('keeps the count while a further page loads, hides it on a fresh load', () => {
		expect(totalLine(120, false, { loading: true, appending: true })).toBe('120 items');
		expect(totalLine(120, false, { loading: true, appending: false })).toBeNull();
		expect(totalLine(0, false, { loading: false, appending: false })).toBeNull();
		expect(totalLine(1000, true, { loading: false, appending: false })).toBe('1,000+ items');
	});

	it('falls back to the item list when the last condition is removed', async () => {
		searchNodes.mockResolvedValue(searchResult({}));
		listNodes.mockResolvedValue({ data: [], response: respond(200) });
		const basics = { type: null, q: '' };
		await loadItemsPage({ filter: readFilter(filterToken(favourite)).query, basics });
		expect(searchNodes).toHaveBeenCalledTimes(1);
		const after = removeAt(favourite, [0]);
		const params = withFilter(new URLSearchParams({ f: encodeQuery(favourite) }), after);
		expect(params.has('f')).toBe(false);
		await loadItemsPage({ filter: readFilter(params.get('f')).query, basics });
		expect(listNodes).toHaveBeenCalledTimes(1);
		expect(searchNodes).toHaveBeenCalledTimes(1);
	});
});
