import { describe, expect, it } from 'vitest';
import { COLLECTION_SORT_CHOICES, sortChoiceFor } from '$lib/list-sort-choices';
import { sortQuery } from '$lib/table-sort';

describe('sortChoiceFor', () => {
	it('finds a choice by the value in the address', () => {
		expect(sortChoiceFor(COLLECTION_SORT_CHOICES, 'name-desc').sort).toEqual({
			key: 'name',
			order: 'desc'
		});
	});

	it("falls back to the route's own order for a value that is none", () => {
		expect(sortChoiceFor(COLLECTION_SORT_CHOICES, 'nonsense').sort).toBeNull();
		expect(sortChoiceFor(COLLECTION_SORT_CHOICES, null).value).toBe('oldest');
	});
});

describe('COLLECTION_SORT_CHOICES', () => {
	it('has a unique value for each choice, and the route default first', () => {
		const values = COLLECTION_SORT_CHOICES.map((c) => c.value);
		expect(new Set(values).size).toBe(values.length);
		expect(COLLECTION_SORT_CHOICES[0].sort).toBeNull();
	});

	it('turns each choice into the parameters the route takes', () => {
		expect(sortQuery(sortChoiceFor(COLLECTION_SORT_CHOICES, 'updated').sort)).toEqual({
			sort: ['updated_at'],
			order: ['desc']
		});
		expect(sortQuery(sortChoiceFor(COLLECTION_SORT_CHOICES, 'oldest').sort)).toEqual({});
	});
});
