import { describe, expect, it } from 'vitest';
import { ariaSort, nextSort, sortQuery, type TableSort } from '$lib/table-sort';

type Key = 'name' | 'created_at';

describe('nextSort', () => {
	it('sorts a new column ascending', () => {
		expect(nextSort<Key>(null, 'name')).toEqual({ key: 'name', order: 'asc' });
	});

	it('goes ascending, descending, then back to the server order on the same column', () => {
		const first = nextSort<Key>(null, 'name');
		const second = nextSort<Key>(first, 'name');
		const third = nextSort<Key>(second, 'name');
		expect(second).toEqual({ key: 'name', order: 'desc' });
		expect(third).toBeNull();
	});

	it('starts a different column ascending, whatever the one before was doing', () => {
		const desc: TableSort<Key> = { key: 'name', order: 'desc' };
		expect(nextSort(desc, 'created_at')).toEqual({ key: 'created_at', order: 'asc' });
	});
});

describe('sortQuery', () => {
	it('is the key and direction as the list routes take them', () => {
		expect(sortQuery<Key>({ key: 'created_at', order: 'desc' })).toEqual({
			sort: ['created_at'],
			order: ['desc']
		});
	});

	it('says nothing for the server order, so its own default applies', () => {
		expect(sortQuery<Key>(null)).toEqual({});
	});
});

describe('ariaSort', () => {
	it('names the direction on the sorted column only', () => {
		const sort: TableSort<Key> = { key: 'name', order: 'asc' };
		expect(ariaSort(sort, 'name')).toBe('ascending');
		expect(ariaSort({ key: 'name', order: 'desc' }, 'name')).toBe('descending');
		expect(ariaSort(sort, 'created_at')).toBe('none');
		expect(ariaSort(null, 'name')).toBe('none');
	});
});
