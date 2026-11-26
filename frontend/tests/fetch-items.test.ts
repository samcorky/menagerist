import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listNodes } = vi.hoisted(() => ({ listNodes: vi.fn() }));
vi.mock('$lib/api/client', () => ({ listNodes }));
import { fetchItems } from '../src/lib/fetch-items';
import { PAGE_LIMIT } from '../src/lib/paging';

const rows = (from: number, count: number) =>
	Array.from({ length: count }, (_, i) => ({ id: `n${from + i}` }));
const page = (data: unknown[], next?: string) => ({
	data,
	response: new Response(null, {
		headers: next ? { link: `</api/v1/nodes?limit=100&after=${next}>; rel="next"` } : {}
	})
});

beforeEach(() => listNodes.mockReset());

describe('fetchItems', () => {
	it('reads items a page at a time, following the cursor', async () => {
		listNodes
			.mockResolvedValueOnce(page(rows(0, 100), 'c1'))
			.mockResolvedValueOnce(page(rows(100, 40)));
		expect(await fetchItems()).toHaveLength(140);
		expect(listNodes).toHaveBeenNthCalledWith(1, {
			query: { after: undefined, limit: PAGE_LIMIT }
		});
		expect(listNodes).toHaveBeenNthCalledWith(2, { query: { after: 'c1', limit: PAGE_LIMIT } });
	});

	it('reads no more than it was asked for', async () => {
		listNodes.mockResolvedValue(page(rows(0, 100), 'more'));
		expect(await fetchItems(250)).toHaveLength(250);
	});

	it('keeps what it loaded when a later page fails', async () => {
		listNodes
			.mockResolvedValueOnce(page(rows(0, 100), 'c1'))
			.mockResolvedValueOnce({ error: { detail: 'boom' }, data: undefined });
		expect(await fetchItems()).toHaveLength(100);
	});
});
