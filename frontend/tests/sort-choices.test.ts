import { describe, expect, it } from 'vitest';
import { emptyQuery } from '$lib/query/tree';
import {
	CUSTOM_SORT,
	SORT_CHOICES,
	nodeSortParams,
	sortChoiceByValue,
	sortChoiceOf,
	withSortChoice
} from '$lib/query/sort-choices';

describe('sortChoiceOf', () => {
	it('knows each choice by the sort it writes', () => {
		for (const choice of SORT_CHOICES) expect(sortChoiceOf(choice.sort)).toBe(choice.value);
	});

	it('calls no sort the plain list, in creation order', () => {
		expect(sortChoiceOf([])).toBe('oldest');
	});

	it('reads a key with no direction as ascending', () => {
		expect(sortChoiceOf([{ by: 'name' }])).toBe('name-asc');
	});

	it('calls anything else custom: another key, two keys, or a field', () => {
		expect(sortChoiceOf([{ by: 'created', dir: 'asc' }])).toBe(CUSTOM_SORT);
		expect(
			sortChoiceOf([
				{ by: 'name', dir: 'asc' },
				{ by: 'updated', dir: 'desc' }
			])
		).toBe(CUSTOM_SORT);
		expect(sortChoiceOf([{ by: 'field', type: 'film', key: 'year', dir: 'asc' }])).toBe(
			CUSTOM_SORT
		);
	});
});

describe('withSortChoice', () => {
	it('writes the sort of a choice and keeps the conditions', () => {
		const where = { op: 'and' as const, children: [{ kind: 'favourite' as const, value: true }] };
		const next = withSortChoice({ ...emptyQuery(), where }, 'newest');
		expect(next.sort).toEqual([{ by: 'created', dir: 'desc' }]);
		expect(next.where).toBe(where);
	});

	it('clears a custom sort for the plain list', () => {
		const custom = { ...emptyQuery(), sort: [{ by: 'field' as const, type: 'film', key: 'year' }] };
		expect(withSortChoice(custom, 'oldest').sort).toEqual([]);
	});

	it('does not share the choice’s keys with the query it makes', () => {
		const first = withSortChoice(emptyQuery(), 'newest');
		first.sort[0].dir = 'asc';
		expect(withSortChoice(emptyQuery(), 'newest').sort[0].dir).toBe('desc');
	});

	it('leaves the query alone for a value that is not a choice', () => {
		const query = emptyQuery();
		expect(withSortChoice(query, CUSTOM_SORT)).toBe(query);
		expect(withSortChoice(query, 'nope')).toBe(query);
	});
});

describe('nodeSortParams', () => {
	it('says nothing for no sort, so the route keeps its own order', () => {
		expect(nodeSortParams([])).toEqual({});
	});

	it('names the keys the item list route takes, each with its direction', () => {
		expect(nodeSortParams([{ by: 'created', dir: 'desc' }])).toEqual({
			sort: ['created_at'],
			order: ['desc']
		});
		expect(nodeSortParams([{ by: 'name' }, { by: 'updated', dir: 'desc' }])).toEqual({
			sort: ['name', 'updated_at'],
			order: ['asc', 'desc']
		});
	});

	it('leaves out a field key, which only the search route sorts by', () => {
		expect(nodeSortParams([{ by: 'field', key: 'year' }])).toEqual({});
	});

	it('turns every choice into parameters the route takes', () => {
		for (const choice of SORT_CHOICES) {
			const params = nodeSortParams(choice.sort);
			expect(params.sort?.length ?? 0).toBe(choice.sort.length);
		}
	});
});

describe('sortChoiceByValue', () => {
	it('finds a choice by the value in the address, and nothing for any other', () => {
		expect(sortChoiceByValue('name-desc')?.sort).toEqual([{ by: 'name', dir: 'desc' }]);
		expect(sortChoiceByValue('saved')).toBeUndefined();
		expect(sortChoiceByValue(null)).toBeUndefined();
	});
});
