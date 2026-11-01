import { describe, expect, it } from 'vitest';
import { decodeQuery, encodeQuery } from '$lib/query/codec';
import { describeCondition, type SummaryLookup } from '$lib/query/summary';
import {
	applyDraft,
	chipModels,
	conditionFor,
	conditionProblem,
	GENERAL_SUBJECTS,
	missingFieldMessage,
	STALE_COLLECTION_MESSAGE,
	subjectOf,
	withCollectionIds,
	withCollectionMode,
	withMediaMode,
	withMediaType,
	withOperator,
	withSubject
} from '$lib/query/builder';
import { DESCRIPTION_OPERATORS, NAME_OPERATORS, operatorsForCondition } from '$lib/query/operators';
import { linkedNarrow, LINKED_TOO_LARGE_MESSAGE } from '$lib/query/narrow';
import { fitsLimits } from '$lib/query/limits';
import { mapWarnings, parseQueryPath } from '$lib/query/warnings';
import { summaryLookup } from '$lib/query/fields';
import { MAX_COLLECTION_IDS, type Condition, type Query } from '$lib/query/types';
import { catalogue } from './query-builder-fixtures';

const A = '018f5c2e-7b1a-7c3e-9d4f-1a2b3c4d5e6f';
const B = '018f5c2e-7b1a-7c3e-9d4f-1a2b3c4d5e70';

const wrap = (...children: unknown[]) => ({
	v: 1,
	where: { op: 'and', children },
	sort: []
});
const roundTrip = (c: unknown) => decodeQuery(encodeQuery(wrap(c) as Query));
const q = (...children: Condition[]): Query => ({
	v: 1,
	where: { op: 'and', children },
	sort: []
});

describe('decoder: description and name', () => {
	it.each([
		{ kind: 'description', op: '~', value: 'signed' },
		{ kind: 'description', op: 'empty' },
		{ kind: 'description', op: 'not_empty' },
		{ kind: 'name', op: '~', value: 'alien' },
		{ kind: 'name', op: '=', value: 'Alien' }
	])('keeps %j', (c) => {
		expect(roundTrip(c)?.where?.children[0]).toEqual(c);
	});

	it.each([
		{ kind: 'description', op: '~' },
		{ kind: 'description', op: '~', value: '' },
		{ kind: 'description', op: 'empty', value: 'x' },
		{ kind: 'description', op: '=', value: 'x' },
		{ kind: 'description', value: 'x' },
		{ kind: 'name', op: 'empty' },
		{ kind: 'name', op: '!=', value: 'x' },
		{ kind: 'name', op: '=', value: 'x'.repeat(201) }
	])('rejects %j', (c) => {
		expect(roundTrip(c)).toBeNull();
	});

	it('drops unknown keys, as for the other kinds', () => {
		const out = roundTrip({ kind: 'name', op: '=', value: 'x', extra: 1 });
		expect(out?.where?.children[0]).toEqual({ kind: 'name', op: '=', value: 'x' });
	});
});

describe('decoder: media and collection', () => {
	it.each([
		{ kind: 'media', mode: 'has' },
		{ kind: 'media', mode: 'none', type: 'document' },
		{ kind: 'collection', mode: 'any', in: [A] },
		{ kind: 'collection', mode: 'none', in: [A, B] }
	])('keeps %j', (c) => {
		expect(roundTrip(c)?.where?.children[0]).toEqual(c);
	});

	it.each([
		{ kind: 'media' },
		{ kind: 'media', mode: 'some' },
		{ kind: 'media', mode: 'has', type: 'video' },
		{ kind: 'collection', mode: 'all', in: [A] },
		{ kind: 'collection', mode: 'any', in: [] },
		{ kind: 'collection', mode: 'any', in: A },
		{ kind: 'collection', mode: 'any', in: ['nope'] },
		{ kind: 'collection', mode: 'any', in: [5] },
		{ kind: 'collection', mode: 'any' }
	])('rejects %j', (c) => {
		expect(roundTrip(c)).toBeNull();
	});

	it('allows 50 collection ids and refuses 51', () => {
		const ids = (n: number) =>
			Array.from({ length: n }, (_, i) => `00000000-0000-0000-0000-${String(i).padStart(12, '0')}`);
		expect(
			roundTrip({ kind: 'collection', mode: 'any', in: ids(MAX_COLLECTION_IDS) })
		).not.toBeNull();
		expect(
			roundTrip({ kind: 'collection', mode: 'any', in: ids(MAX_COLLECTION_IDS + 1) })
		).toBeNull();
	});
});

describe('operator tables', () => {
	it('lists the operators of description and name', () => {
		expect(DESCRIPTION_OPERATORS).toEqual(['~', 'empty', 'not_empty']);
		expect(NAME_OPERATORS).toEqual(['~', '=']);
		expect(operatorsForCondition('description')).toBe(DESCRIPTION_OPERATORS);
		expect(operatorsForCondition('name')).toBe(NAME_OPERATORS);
	});
});

const names: Record<string, string> = { [A]: 'Watchlist', [B]: 'Films' };
const lookup: SummaryLookup = {
	typeLabel: (s) => s,
	fieldLabel: (_t, k) => k,
	collectionName: (id) => (id in names ? names[id] : null)
};

describe('describeCondition: new kinds', () => {
	it.each([
		[{ kind: 'description', op: '~', value: 'signed' }, 'Description contains “signed”'],
		[{ kind: 'description', op: 'empty' }, 'Description is empty'],
		[{ kind: 'description', op: 'not_empty' }, 'Description is not empty'],
		[{ kind: 'name', op: '=', value: 'Alien' }, 'Name is “Alien”'],
		[{ kind: 'name', op: '~', value: 'ali' }, 'Name contains “ali”'],
		[{ kind: 'media', mode: 'has' }, 'Has media'],
		[{ kind: 'media', mode: 'has', type: 'image' }, 'Has an image'],
		[{ kind: 'media', mode: 'has', type: 'document' }, 'Has a document'],
		[{ kind: 'media', mode: 'none' }, 'Has no media'],
		[{ kind: 'media', mode: 'none', type: 'image' }, 'Has no image'],
		[{ kind: 'collection', mode: 'any', in: [A] }, 'In Watchlist'],
		[{ kind: 'collection', mode: 'none', in: [A] }, 'Not in Watchlist'],
		[{ kind: 'collection', mode: 'any', in: [A, B] }, 'In any of Watchlist, Films'],
		[{ kind: 'collection', mode: 'none', in: [A, B] }, 'In none of Watchlist, Films']
	] as const)('%j', (c, expected) => {
		expect(describeCondition(c as Condition, lookup)).toBe(expected);
	});

	it('names a collection that is gone', () => {
		const gone = '018f5c2e-7b1a-7c3e-9d4f-000000000000';
		expect(describeCondition({ kind: 'collection', mode: 'any', in: [gone] }, lookup)).toBe(
			'In a collection that no longer exists'
		);
		expect(describeCondition({ kind: 'collection', mode: 'none', in: [gone, A] }, lookup)).toBe(
			'In none of a collection that no longer exists, Watchlist'
		);
	});

	it('says only "a collection" until names are loaded', () => {
		const loading = { ...lookup, collectionName: () => undefined };
		expect(describeCondition({ kind: 'collection', mode: 'none', in: [A] }, loading)).toBe(
			'Not in a collection'
		);
		const bare = { typeLabel: (s: string) => s, fieldLabel: (_t: string, k: string) => k };
		expect(describeCondition({ kind: 'collection', mode: 'any', in: [A] }, bare)).toBe(
			'In a collection'
		);
	});

	it('uses no developer terms', () => {
		const words = [
			{ kind: 'description', op: 'empty' },
			{ kind: 'media', mode: 'none', type: 'image' },
			{ kind: 'collection', mode: 'any', in: [A] }
		].map((c) => describeCondition(c as Condition, lookup));
		for (const text of words) expect(text).not.toMatch(/node|edge|graph/i);
	});

	it('summaryLookup passes a collection name lookup through', () => {
		const l = summaryLookup(catalogue, (id) => (id === A ? 'Watchlist' : null));
		expect(l.collectionName?.(A)).toBe('Watchlist');
		expect(summaryLookup(catalogue).collectionName?.(A)).toBeUndefined();
	});
});

describe('builder: subjects and defaults', () => {
	it('offers the four new subjects', () => {
		const values = GENERAL_SUBJECTS.map((s) => s.value);
		expect(values).toEqual(expect.arrayContaining(['description', 'name', 'media', 'collection']));
	});

	it.each([
		['description', { kind: 'description', op: '~', value: '' }],
		['name', { kind: 'name', op: '~', value: '' }],
		['media', { kind: 'media', mode: 'has' }],
		['collection', { kind: 'collection', mode: 'any', in: [] }]
	])('a new %s row starts as %j', (subject, expected) => {
		const c = conditionFor(subject, catalogue);
		expect(c).toEqual(expected);
		expect(subjectOf(c)).toBe(subject);
	});

	it('switching subject resets the row', () => {
		const c = withSubject({ kind: 'text', q: 'x' }, 'media', catalogue);
		expect(c).toEqual({ kind: 'media', mode: 'has' });
	});
});

describe('builder: operator and mode edits', () => {
	it('drops the value for a no-value description operator and restores it for ~', () => {
		const contains: Condition = { kind: 'description', op: '~', value: 'x' };
		const empty = withOperator(contains, 'empty', catalogue);
		expect(empty).toEqual({ kind: 'description', op: 'empty' });
		expect(withOperator(empty, 'not_empty', catalogue)).toEqual({
			kind: 'description',
			op: 'not_empty'
		});
		expect(withOperator(empty, '~', catalogue)).toEqual({
			kind: 'description',
			op: '~',
			value: ''
		});
		expect(withOperator(contains, '~', catalogue)).toBe(contains);
	});

	it('keeps the name value across ~ and =', () => {
		expect(withOperator({ kind: 'name', op: '~', value: 'a' }, '=', catalogue)).toEqual({
			kind: 'name',
			op: '=',
			value: 'a'
		});
	});

	it('ignores an operator the kind does not have', () => {
		const c: Condition = { kind: 'name', op: '=', value: 'a' };
		expect(withOperator(c, 'empty', catalogue)).toBe(c);
	});

	it('sets the media mode and type, removing the type key for any', () => {
		const c: Condition = { kind: 'media', mode: 'has', type: 'image' };
		expect(withMediaMode(c, 'none')).toEqual({ kind: 'media', mode: 'none', type: 'image' });
		expect(withMediaType(c, null)).toEqual({ kind: 'media', mode: 'has' });
		expect(withMediaType({ kind: 'media', mode: 'has' }, 'document')).toEqual({
			kind: 'media',
			mode: 'has',
			type: 'document'
		});
	});

	it('sets the collection mode and ids without duplicates, capped at 50', () => {
		const c: Condition = { kind: 'collection', mode: 'any', in: [A] };
		expect(withCollectionMode(c, 'none')).toEqual({ kind: 'collection', mode: 'none', in: [A] });
		expect(withCollectionIds(c, [A, B, A])).toEqual({
			kind: 'collection',
			mode: 'any',
			in: [A, B]
		});
		const many = Array.from({ length: 60 }, (_, i) => `id-${i}`);
		expect((withCollectionIds(c, many) as { in: string[] }).in).toHaveLength(MAX_COLLECTION_IDS);
	});

	it('leaves other kinds alone', () => {
		const fav: Condition = { kind: 'favourite', value: true };
		expect(withMediaMode(fav, 'none')).toBe(fav);
		expect(withMediaType(fav, 'image')).toBe(fav);
		expect(withCollectionMode(fav, 'none')).toBe(fav);
		expect(withCollectionIds(fav, [A])).toBe(fav);
	});
});

describe('builder: validation', () => {
	const problem = (c: Condition) => conditionProblem(c, catalogue);

	it('needs words for ~ and = and none for the empty tests', () => {
		expect(problem({ kind: 'description', op: '~', value: '' })).toBe(
			'Enter some words to look for.'
		);
		expect(problem({ kind: 'description', op: '~', value: '   ' })).not.toBeNull();
		expect(problem({ kind: 'description', op: '~', value: 'a'.repeat(201) })).toBe(
			'Use 200 characters or fewer.'
		);
		expect(problem({ kind: 'description', op: '~', value: 'signed' })).toBeNull();
		expect(problem({ kind: 'description', op: 'empty' })).toBeNull();
		expect(problem({ kind: 'name', op: '=', value: '' })).toBe('Enter a name.');
		expect(problem({ kind: 'name', op: '=', value: 'Alien' })).toBeNull();
		expect(problem({ kind: 'name', op: '~', value: '' })).toBe('Enter some words to look for.');
	});

	it('always accepts media and needs a collection for the collection row', () => {
		expect(problem({ kind: 'media', mode: 'none' })).toBeNull();
		expect(problem({ kind: 'collection', mode: 'any', in: [] })).toBe(
			'Choose at least one collection.'
		);
		expect(problem({ kind: 'collection', mode: 'any', in: [A] })).toBeNull();
		const many = Array.from({ length: 51 }, () => A);
		expect(problem({ kind: 'collection', mode: 'any', in: many })).toBe(
			'Choose 50 collections or fewer.'
		);
	});

	it('applyDraft drops unfinished new rows', () => {
		const draft = q(
			{ kind: 'description', op: '~', value: '' },
			{ kind: 'collection', mode: 'any', in: [] },
			{ kind: 'media', mode: 'has' }
		);
		expect(applyDraft(draft, catalogue).query.where?.children).toEqual([
			{ kind: 'media', mode: 'has' }
		]);
	});
});

describe('warnings for collection conditions', () => {
	it('maps a stale id inside a collection row to that row', () => {
		expect(parseQueryPath('where.children[1].in[0]')).toEqual({ where: [1] });
		expect(parseQueryPath('where.children[1].children[2].in[3].children[0]')).toEqual({
			where: [1, 2]
		});
		expect([...mapWarnings([{ path: 'where.children[0].in[2]' }]).conditions]).toEqual(['0']);
	});

	it('still ignores other unknown paths', () => {
		expect(parseQueryPath('where.in[0]')).toEqual({ where: [] });
		expect(parseQueryPath('in[0]')).toBeNull();
		expect(parseQueryPath('where.children[0].inx[1]')).toBeNull();
	});

	it('words the warning for a collection row', () => {
		expect(missingFieldMessage({ kind: 'collection', mode: 'any', in: [A] })).toBe(
			STALE_COLLECTION_MESSAGE
		);
		expect(STALE_COLLECTION_MESSAGE).toBe(
			'A collection here no longer exists, so it matches nothing.'
		);
	});

	it('flags the chip of a stale collection row', () => {
		const query = q({ kind: 'collection', mode: 'any', in: [A] });
		const { chips } = chipModels(query, lookup, new Set(['0']));
		expect(chips[0].text).toBe('In Watchlist');
		expect(chips[0].warning).toBe(true);
		expect(chips[0].message).toBe(STALE_COLLECTION_MESSAGE);
	});
});

describe('linkedNarrow', () => {
	const adhoc = q({ kind: 'favourite', value: true }, { kind: 'tag', mode: 'any', tags: ['red'] });

	it('puts "in collection" first and merges an and-filter flat', () => {
		const out = linkedNarrow(A, adhoc);
		expect(out).toEqual({
			v: 1,
			where: {
				op: 'and',
				children: [{ kind: 'collection', mode: 'any', in: [A] }, ...(adhoc.where?.children ?? [])]
			},
			sort: []
		});
	});

	it('nests an or-filter as one child and keeps its sort', () => {
		const or: Query = {
			v: 1,
			where: { op: 'or', children: [{ kind: 'favourite', value: true }] },
			sort: [{ by: 'name' }]
		};
		const out = linkedNarrow(A, or);
		expect(out?.where?.children[1]).toEqual(or.where);
		expect(out?.sort).toEqual([{ by: 'name' }]);
	});

	it('is just the collection condition for an empty filter', () => {
		expect(linkedNarrow(A, { v: 1, where: null, sort: [] })?.where?.children).toEqual([
			{ kind: 'collection', mode: 'any', in: [A] }
		]);
	});

	it('returns null when the result would break a limit', () => {
		const full = q(
			...Array.from({ length: 50 }, (): Condition => ({ kind: 'favourite', value: true }))
		);
		expect(linkedNarrow(A, full)).toBeNull();
		const fits = linkedNarrow(
			A,
			q(...Array.from({ length: 49 }, (): Condition => ({ kind: 'favourite', value: true })))
		);
		expect(fits && fitsLimits(fits)).toBe(true);
		expect(LINKED_TOO_LARGE_MESSAGE).toMatch(/too many/i);
	});

	it('returns null when the filter is already at the depth limit', () => {
		const deep: Query = {
			v: 1,
			where: {
				op: 'or',
				children: [
					{
						op: 'or',
						children: [
							{ op: 'or', children: [{ op: 'or', children: [{ kind: 'favourite', value: true }] }] }
						]
					}
				]
			},
			sort: []
		};
		expect(linkedNarrow(A, deep)).toBeNull();
	});

	it('does not change its inputs', () => {
		const before = JSON.stringify(adhoc);
		linkedNarrow(A, adhoc);
		expect(JSON.stringify(adhoc)).toBe(before);
	});
});
