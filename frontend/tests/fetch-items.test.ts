import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listNodes } = vi.hoisted(() => ({ listNodes: vi.fn() }));
vi.mock('$lib/api/client', () => ({ listNodes }));
import { fetchItemsById } from '../src/lib/fetch-items';
import { PAGE_LIMIT } from '../src/lib/paging';

const ids = (count: number) => Array.from({ length: count }, (_, i) => `n${i}`);
const found = (rows: string[]) => ({ data: rows.map((id) => ({ id })) });

beforeEach(() => listNodes.mockReset());

describe('fetchItemsById', () => {
	it('reads the items in one request, once for each id', async () => {
		listNodes.mockResolvedValue(found(['a', 'b']));
		expect(await fetchItemsById(['a', 'b', 'a'])).toEqual([{ id: 'a' }, { id: 'b' }]);
		expect(listNodes).toHaveBeenCalledTimes(1);
		expect(listNodes).toHaveBeenCalledWith({ query: { id: ['a', 'b'], limit: PAGE_LIMIT } });
	});

	it('reads nothing for no ids', async () => {
		expect(await fetchItemsById([])).toEqual([]);
		expect(listNodes).not.toHaveBeenCalled();
	});

	it('splits more ids than a request takes', async () => {
		listNodes.mockResolvedValueOnce(found(ids(PAGE_LIMIT))).mockResolvedValueOnce(found(ids(5)));
		expect(await fetchItemsById(ids(PAGE_LIMIT + 5))).toHaveLength(PAGE_LIMIT + 5);
		expect(listNodes).toHaveBeenCalledTimes(2);
	});

	it('keeps what it read when one request fails', async () => {
		listNodes
			.mockResolvedValueOnce(found(ids(PAGE_LIMIT)))
			.mockResolvedValueOnce({ error: { detail: 'boom' }, data: undefined });
		expect(await fetchItemsById(ids(PAGE_LIMIT + 5))).toHaveLength(PAGE_LIMIT);
	});
});
