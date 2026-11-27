import { describe, expect, it } from 'vitest';
import { listTableState } from '$lib/list-table';

describe('listTableState', () => {
	it('shows the skeleton only while the first read has no rows yet', () => {
		expect(listTableState({ error: null, loading: true, rows: 0 })).toBe('loading');
	});

	it('keeps the rows on screen while they are read again', () => {
		expect(listTableState({ error: null, loading: true, rows: 3 })).toBe('rows');
		expect(listTableState({ error: null, loading: false, rows: 3 })).toBe('rows');
	});

	it('says empty only once a read has finished with nothing', () => {
		expect(listTableState({ error: null, loading: false, rows: 0 })).toBe('empty');
	});

	it('shows a failure in place of everything else', () => {
		expect(listTableState({ error: 'Could not load tokens.', loading: false, rows: 0 })).toBe(
			'error'
		);
		expect(listTableState({ error: 'Could not load tokens.', loading: true, rows: 3 })).toBe(
			'error'
		);
	});

	it('treats no error as an empty value of any kind', () => {
		expect(listTableState({ error: '', loading: false, rows: 1 })).toBe('rows');
		expect(listTableState({ error: undefined, loading: false, rows: 1 })).toBe('rows');
	});
});
