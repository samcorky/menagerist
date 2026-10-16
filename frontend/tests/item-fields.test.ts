import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listItemFields } = vi.hoisted(() => ({ listItemFields: vi.fn() }));
vi.mock('$lib/api/client', () => ({ listItemFields }));

import { fetchItemFields } from '$lib/item-fields';

beforeEach(() => vi.resetAllMocks());

describe('fetchItemFields', () => {
	it('returns the listing', async () => {
		const rows = [{ key: 'signed', kind: 'boolean', label: 'Signed', count: 3 }];
		listItemFields.mockResolvedValueOnce({ data: rows });
		expect(await fetchItemFields()).toEqual(rows);
		expect(listItemFields).toHaveBeenCalledTimes(1);
	});

	it('returns null on an error response', async () => {
		listItemFields.mockResolvedValueOnce({ error: { detail: 'nope' } });
		expect(await fetchItemFields()).toBeNull();
	});

	it('returns null when there is no data', async () => {
		listItemFields.mockResolvedValueOnce({});
		expect(await fetchItemFields()).toBeNull();
	});

	it('returns null when the request throws', async () => {
		listItemFields.mockRejectedValueOnce(new Error('offline'));
		expect(await fetchItemFields()).toBeNull();
	});
});
