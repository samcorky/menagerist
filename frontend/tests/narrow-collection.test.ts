import { describe, expect, it } from 'vitest';
import {
	SAVE_TEXT_TOO_LONG_MESSAGE,
	SAVE_TOO_LARGE_MESSAGE,
	combineWithSaved,
	locateInCombined,
	narrowFilterCount,
	narrowedBarText,
	narrowedMarks,
	needsNarrowing,
	saveBlockReason,
	updateConfirmation
} from '$lib/query/narrow';
import { fitsLimits } from '$lib/query/limits';
import { emptyQuery } from '$lib/query/tree';
import type { Condition, Group, Query } from '$lib/query/types';

const fav: Condition = { kind: 'favourite', value: true };
const wine: Condition = { kind: 'type', in: ['wine'] };
const text = (q: string): Condition => ({ kind: 'text', q });
const tag: Condition = { kind: 'tag', mode: 'any', tags: ['red'] };
const and = (...children: Group['children']): Group => ({ op: 'and', children });
const or = (...children: Group['children']): Group => ({ op: 'or', children });
const query = (where: Group | null, sort: Query['sort'] = []): Query => ({ v: 1, where, sort });

describe('combineWithSaved', () => {
	it('returns the saved tree when nothing narrows it', () => {
		const saved = query(and(fav, wine), [{ by: 'name', dir: 'desc' }]);
		expect(combineWithSaved(saved, emptyQuery())).toEqual(saved);
		expect(combineWithSaved(saved, emptyQuery(), { q: '  ', type: '' })).toEqual(saved);
	});

	it('does not wrap an or root when there is nothing to add', () => {
		const saved = query(or(fav, wine));
		expect(combineWithSaved(saved, emptyQuery()).where).toEqual(or(fav, wine));
	});

	it('ANDs the ad-hoc conditions onto an and root without adding a level', () => {
		const combined = combineWithSaved(query(and(fav)), query(and(wine)));
		expect(combined.where).toEqual(and(fav, wine));
	});

	it('keeps an or root as a single child of the new and', () => {
		const combined = combineWithSaved(query(or(fav, wine)), query(and(tag)));
		expect(combined.where).toEqual(and(or(fav, wine), tag));
	});

	it('uses the ad-hoc tree alone when the saved one has no conditions', () => {
		expect(combineWithSaved(emptyQuery(), query(and(tag))).where).toEqual(and(tag));
	});

	it('turns the search text and the type into conditions', () => {
		const combined = combineWithSaved(query(and(fav)), emptyQuery(), {
			q: ' claret ',
			type: 'wine'
		});
		expect(combined.where).toEqual(and(fav, { kind: 'type', in: ['wine'] }, text('claret')));
	});

	it('uses the saved sort unless the ad-hoc builder set one', () => {
		const saved = query(and(fav), [{ by: 'name', dir: 'asc' }]);
		expect(combineWithSaved(saved, query(and(tag))).sort).toEqual([{ by: 'name', dir: 'asc' }]);
		const adhoc = query(and(tag), [{ by: 'created', dir: 'desc' }]);
		expect(combineWithSaved(saved, adhoc).sort).toEqual([{ by: 'created', dir: 'desc' }]);
	});

	it('goes over the limits when too many conditions are combined', () => {
		const many = (n: number): Condition[] =>
			Array.from({ length: n }, (_, i) => ({ kind: 'tag', mode: 'any', tags: [`t${i}`] }));
		const saved = query(and(...many(30)));
		expect(fitsLimits(combineWithSaved(saved, query(and(...many(20)))))).toBe(true);
		expect(fitsLimits(combineWithSaved(saved, query(and(...many(21)))))).toBe(false);
	});

	it('goes over the depth limit when an or root is wrapped', () => {
		const deep = or(and(or(and(fav))));
		expect(fitsLimits(query(deep))).toBe(true);
		expect(fitsLimits(combineWithSaved(query(deep), query(and(tag))))).toBe(false);
	});
});

describe('narrowFilterCount and needsNarrowing', () => {
	it('counts conditions, the search and the type', () => {
		expect(narrowFilterCount(emptyQuery(), {})).toBe(0);
		expect(narrowFilterCount(query(and(fav, tag)), {})).toBe(2);
		expect(narrowFilterCount(query(and(fav)), { q: 'x', type: 'wine' })).toBe(3);
		expect(narrowFilterCount(emptyQuery(), { q: '   ' })).toBe(0);
	});

	it('also needs a search when only the sort changed', () => {
		expect(needsNarrowing(emptyQuery(), {})).toBe(false);
		expect(needsNarrowing(query(null, [{ by: 'name' }]), {})).toBe(true);
		expect(needsNarrowing(emptyQuery(), { q: 'x' })).toBe(true);
	});
});

describe('narrowedBarText', () => {
	it('reads as a count of the filters and of the items', () => {
		expect(narrowedBarText(2, { total: 3, capped: false }, { count: 12, capped: false })).toBe(
			'Narrowed by 2 filters: 3 of 12 items'
		);
	});

	it('uses the singular for one filter and one item', () => {
		expect(narrowedBarText(1, { total: 1, capped: false }, { count: 1, capped: false })).toBe(
			'Narrowed by 1 filter: 1 of 1 item'
		);
	});

	it('uses the capped label for both counts', () => {
		expect(narrowedBarText(1, { total: 1000, capped: true }, { count: 1000, capped: true })).toBe(
			'Narrowed by 1 filter: 1,000+ of 1,000+ items'
		);
	});

	it('leaves the counts out until the results are in', () => {
		expect(narrowedBarText(2, null, { count: 12, capped: false })).toBe('Narrowed by 2 filters');
	});

	it('says so when only the order differs', () => {
		expect(narrowedBarText(0, { total: 4, capped: false }, { count: 4, capped: false })).toBe(
			'Sorted differently: 4 of 4 items'
		);
	});
});

describe('saveBlockReason', () => {
	it('allows a combination that fits', () => {
		expect(saveBlockReason(query(and(fav)), query(and(tag)), { q: 'x' })).toBeNull();
	});

	it('explains when the combination is too large', () => {
		const tags = Array.from({ length: 30 }, (_, i): Condition => ({ ...tag, tags: [`t${i}`] }));
		expect(saveBlockReason(query(and(...tags)), query(and(...tags)), {})).toBe(
			SAVE_TOO_LARGE_MESSAGE
		);
	});

	it('explains when the search text is too long to save', () => {
		expect(saveBlockReason(query(and(fav)), emptyQuery(), { q: 'x'.repeat(201) })).toBe(
			SAVE_TEXT_TOO_LONG_MESSAGE
		);
	});
});

describe('updateConfirmation', () => {
	it('states what will change', () => {
		const text = updateConfirmation(2, 3);
		expect(text).toContain('2 conditions');
		expect(text).toContain('3 conditions');
		expect(text).toMatch(/replace/i);
		expect(text).toMatch(/leave this collection/i);
	});

	it('uses the singular', () => {
		expect(updateConfirmation(1, 2)).toContain('1 condition ');
	});

	it('mentions the sort only when the sort is being replaced', () => {
		expect(updateConfirmation(2, 3)).not.toMatch(/sort/i);
		expect(updateConfirmation(2, 3, true)).toContain('and replaces the sort');
	});
});

describe('locateInCombined', () => {
	const saved = query(and(fav, wine));
	it('maps a path to the saved part', () => {
		expect(locateInCombined([1], saved, query(and(tag)), {})).toEqual({
			part: 'saved',
			path: [1]
		});
	});

	it('maps a path to the ad-hoc part of a flat and', () => {
		expect(locateInCombined([2], saved, query(and(tag)), {})).toEqual({
			part: 'adhoc',
			path: [0]
		});
	});

	it('maps through an or root on either side', () => {
		const orSaved = query(or(fav, wine));
		expect(locateInCombined([0, 1], orSaved, query(and(tag)), {})).toEqual({
			part: 'saved',
			path: [1]
		});
		expect(locateInCombined([2, 0], saved, query(or(tag, fav)), {})).toEqual({
			part: 'adhoc',
			path: [0]
		});
	});

	it('maps straight through when the other side has no conditions', () => {
		expect(locateInCombined([1], saved, emptyQuery(), {})).toEqual({ part: 'saved', path: [1] });
		expect(locateInCombined([1], emptyQuery(), query(and(tag, fav)), {})).toEqual({
			part: 'adhoc',
			path: [1]
		});
	});

	it('ignores the conditions added for the search box', () => {
		expect(locateInCombined([3], saved, query(and(tag)), { q: 'x', type: 'wine' })).toBeNull();
		expect(locateInCombined([2], saved, query(and(tag)), { q: 'x' })).toEqual({
			part: 'adhoc',
			path: [0]
		});
	});

	it('finds an ad-hoc or root that was wrapped by the search box', () => {
		expect(locateInCombined([3], saved, query(or(tag, fav)), { q: 'x' })).toBeNull();
		expect(locateInCombined([2, 1], saved, query(or(tag, fav)), { q: 'x' })).toEqual({
			part: 'adhoc',
			path: [1]
		});
	});
});

describe('narrowedMarks', () => {
	it('marks the ad-hoc conditions the server could not match', () => {
		const marks = narrowedMarks(
			[
				{ path: 'where.children[2]', message: 'gone' },
				{ path: 'sort[0]', message: 'gone' }
			],
			query(and(fav, wine)),
			query(and(tag)),
			{}
		);
		expect([...marks.conditions]).toEqual(['0']);
		expect(marks.sort).toBe(true);
	});

	it('leaves out warnings about the saved part', () => {
		const marks = narrowedMarks(
			[{ path: 'where.children[0]', message: 'gone' }],
			query(and(fav, wine)),
			query(and(tag)),
			{}
		);
		expect(marks.conditions.size).toBe(0);
	});
});
