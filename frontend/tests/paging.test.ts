import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listNodes } = vi.hoisted(() => ({ listNodes: vi.fn() }));
vi.mock('$lib/api/client', () => ({ listNodes }));
import { fetchItems, nextCursor, PAGE_LIMIT } from '../src/lib/paging';

const rows = (from: number, count: number) =>
	Array.from({ length: count }, (_, i) => ({ id: `n${from + i}` }));
const page = (data: unknown[], next?: string) => ({
	data,
	response: {
		headers: new Headers(
			next ? { link: `</api/v1/nodes?limit=100&after=${next}>; rel="next"` } : {}
		)
	}
});

beforeEach(() => listNodes.mockReset());

describe('nextCursor', () => {
	it('reads the cursor the next link carries, decoded', () => {
		expect(nextCursor('</x?limit=2&after=eyJ2IjoxfQ>; rel="next"')).toBe('eyJ2IjoxfQ');
		expect(nextCursor('</x?after=a%20b>; rel="next"')).toBe('a b');
	});
	it('is null without a next link, a cursor or a readable one', () => {
		expect(nextCursor(null)).toBeNull();
		expect(nextCursor('</x?after=a>; rel="prev"')).toBeNull();
		expect(nextCursor('</x>; rel="next"')).toBeNull();
		expect(nextCursor('</x?after=%E0%A4%A>; rel="next"')).toBeNull();
	});
});

describe('fetchItems', () => {
	it('follows the next cursor a page at a time until there is none', async () => {
		listNodes
			.mockResolvedValueOnce(page(rows(0, 100), 'c1'))
			.mockResolvedValueOnce(page(rows(100, 40)));
		const items = await fetchItems();
		expect(items).toHaveLength(140);
		expect(listNodes).toHaveBeenNthCalledWith(1, {
			query: { after: undefined, limit: PAGE_LIMIT }
		});
		expect(listNodes).toHaveBeenNthCalledWith(2, { query: { after: 'c1', limit: PAGE_LIMIT } });
	});

	it('stops at the most it was asked for', async () => {
		listNodes.mockResolvedValue(page(rows(0, 100), 'more'));
		const items = await fetchItems(250);
		expect(items).toHaveLength(250);
		expect(listNodes).toHaveBeenCalledTimes(3);
	});

	it('keeps what it loaded when a later page fails', async () => {
		listNodes
			.mockResolvedValueOnce(page(rows(0, 100), 'c1'))
			.mockResolvedValueOnce({ error: { detail: 'boom' }, data: undefined });
		expect(await fetchItems()).toHaveLength(100);
	});
});
