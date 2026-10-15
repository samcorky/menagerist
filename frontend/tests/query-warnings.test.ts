import { describe, expect, it } from 'vitest';
import {
	mapWarnings,
	parseQueryPath,
	pathKey,
	splitDetail,
	toFilterPath
} from '$lib/query/warnings';

describe('parseQueryPath', () => {
	it.each([
		['where', { where: [] }],
		['where.children[2]', { where: [2] }],
		['where.children[2].children[0]', { where: [2, 0] }],
		['where.children[1].children[3].children[0]', { where: [1, 3, 0] }],
		['sort[0]', { sort: 0 }],
		['sort[2]', { sort: 2 }]
	])('%s', (path, expected) => {
		expect(parseQueryPath(path)).toEqual(expected);
	});

	it.each([
		'',
		'where.children',
		'where.children[x]',
		'children[0]',
		'sort',
		'sort[-1]',
		'where[0]'
	])('ignores %j', (path) => {
		expect(parseQueryPath(path)).toBeNull();
	});
});

describe('toFilterPath', () => {
	it('keeps a path when the filter is the sent tree', () => {
		expect(toFilterPath([2, 0], [])).toEqual([2, 0]);
	});

	it('strips the wrapper the page filters added', () => {
		expect(toFilterPath([0, 1], [0])).toEqual([1]);
	});

	it('returns null for a path outside the filter', () => {
		expect(toFilterPath([1], [0])).toBeNull();
		expect(toFilterPath([0], [0])).toBeNull();
	});
});

describe('mapWarnings', () => {
	it('marks nested conditions by path key', () => {
		const marks = mapWarnings([
			{ path: 'where.children[0]' },
			{ path: 'where.children[2].children[1]' }
		]);
		expect([...marks.conditions]).toEqual(['0', '2.1']);
		expect(marks.sort).toBe(false);
	});

	it('maps sort warnings to the sort control', () => {
		const marks = mapWarnings([{ path: 'sort[0]' }]);
		expect(marks.sort).toBe(true);
		expect(marks.conditions.size).toBe(0);
	});

	it('ignores paths it cannot read', () => {
		const marks = mapWarnings([{ path: 'nonsense' }, { path: 'where.children[x]' }]);
		expect(marks.conditions.size).toBe(0);
		expect(marks.sort).toBe(false);
	});

	it('maps through a prefix', () => {
		const marks = mapWarnings([{ path: 'where.children[0].children[1]' }], [0]);
		expect([...marks.conditions]).toEqual([pathKey([1])]);
	});
});

describe('splitDetail', () => {
	it('splits a path from the message', () => {
		expect(splitDetail('where.children[1]: That value does not fit a number field.')).toEqual({
			target: { where: [1] },
			message: 'That value does not fit a number field.'
		});
	});

	it('keeps a plain message whole', () => {
		expect(splitDetail('Something odd: here')).toEqual({
			target: null,
			message: 'Something odd: here'
		});
	});
});
