import { describe, expect, it } from 'vitest';
import {
	addCondition,
	addGroup,
	combine,
	countConditions,
	emptyQuery,
	isFilterEmpty,
	pageConditions,
	removeAt,
	replaceAt,
	searchTextTooLong
} from '$lib/query/tree';
import { isGroup, type Condition, type Group, type Query } from '$lib/query/types';

const fav: Condition = { kind: 'favourite', value: true };
const text: Condition = { kind: 'text', q: 'alien' };

function deepFreeze<T>(value: T): T {
	if (value && typeof value === 'object') {
		Object.freeze(value);
		for (const child of Object.values(value)) deepFreeze(child);
	}
	return value;
}

const frozen = (q: Query) => deepFreeze(structuredClone(q));

describe('query tree', () => {
	it('starts empty and adds conditions to the root', () => {
		const q = addCondition(emptyQuery(), [], fav);
		expect(q.where).toEqual({ op: 'and', children: [fav] });
		expect(countConditions(q)).toBe(1);
		expect(isFilterEmpty(emptyQuery())).toBe(true);
		expect(isFilterEmpty(q)).toBe(false);
	});

	it('adds a nested group and puts conditions in it', () => {
		let q = addCondition(emptyQuery(), [], fav);
		q = addGroup(q, [], 'or');
		q = addCondition(q, [1], text);
		expect(q.where).toEqual({ op: 'and', children: [fav, { op: 'or', children: [text] }] });
		expect(countConditions(q)).toBe(2);
	});

	it('addGroup keeps the new empty group, unlike every other operation', () => {
		const q = addGroup(emptyQuery(), [], 'or');
		expect(q.where).toEqual({ op: 'and', children: [{ op: 'or', children: [] }] });
		expect(isFilterEmpty(q)).toBe(true);
		// Any later pruning edit drops the group again.
		expect(removeAt(addCondition(q, [], fav), [1]).where).toEqual({ op: 'and', children: [fav] });
	});

	it('removes a node, and prunes a group left empty', () => {
		let q = addGroup(addCondition(emptyQuery(), [], fav), [], 'or');
		q = addCondition(q, [1], text);
		q = removeAt(q, [1, 0]);
		expect(q.where).toEqual({ op: 'and', children: [fav] });
	});

	it('removing the last condition clears the filter', () => {
		expect(removeAt(addCondition(emptyQuery(), [], fav), [0]).where).toBeNull();
	});

	it('removing a whole group removes it with its children', () => {
		let q = addCondition(addGroup(addCondition(emptyQuery(), [], fav), [], 'or'), [1], text);
		q = removeAt(q, [1]);
		expect(q.where).toEqual({ op: 'and', children: [fav] });
	});

	it('replaces a condition in place without mutating the input', () => {
		const q = addCondition(emptyQuery(), [], fav);
		const next = replaceAt(q, [0], text);
		expect(next.where).toEqual({ op: 'and', children: [text] });
		expect(q.where).toEqual({ op: 'and', children: [fav] });
	});

	it('replaces a group, for example to change its operator', () => {
		let q = addCondition(addGroup(emptyQuery(), [], 'or'), [0], fav);
		q = replaceAt(q, [0], { op: 'and', children: [fav] });
		expect(q.where).toEqual({ op: 'and', children: [{ op: 'and', children: [fav] }] });
	});

	it('keeps the sort when editing', () => {
		const q: Query = { v: 1, where: null, sort: [{ by: 'name' }] };
		expect(addCondition(q, [], fav).sort).toEqual([{ by: 'name' }]);
	});

	it('never mutates its input', () => {
		const base = frozen(
			addCondition(addGroup(addCondition(emptyQuery(), [], fav), [], 'or'), [1], text)
		);
		expect(() => {
			addCondition(base, [], text);
			addCondition(base, [1], fav);
			addGroup(base, [], 'not');
			removeAt(base, [1, 0]);
			removeAt(base, [0]);
			replaceAt(base, [0], text);
			combine(base, { type: 'film', q: 'x', favourite: true });
		}).not.toThrow();
	});

	describe('invalid paths leave the query unchanged', () => {
		const base = addCondition(addGroup(addCondition(emptyQuery(), [], fav), [], 'or'), [1], text);
		it.each([
			['addCondition into a missing group', (q: Query) => addCondition(q, [5], text)],
			['addCondition into a condition', (q: Query) => addCondition(q, [0], text)],
			['addCondition below a negative index', (q: Query) => addCondition(q, [-1], text)],
			['addGroup into a missing group', (q: Query) => addGroup(q, [9, 9], 'or')],
			['removeAt a missing index', (q: Query) => removeAt(q, [7])],
			['removeAt through a condition', (q: Query) => removeAt(q, [0, 0])],
			['removeAt a fractional index', (q: Query) => removeAt(q, [0.5])],
			['replaceAt a missing index', (q: Query) => replaceAt(q, [7], text)],
			['replaceAt through a condition', (q: Query) => replaceAt(q, [0, 0], text)]
		])('%s', (_name, run) => {
			expect(run(base)).toBe(base);
		});

		it('on an empty query', () => {
			const empty = emptyQuery();
			expect(removeAt(empty, [0])).toBe(empty);
			expect(replaceAt(empty, [0], fav)).toBe(empty);
			expect(addCondition(empty, [0], fav)).toBe(empty);
		});
	});

	it('removeAt with the root path clears the filter', () => {
		expect(removeAt(addCondition(emptyQuery(), [], fav), []).where).toBeNull();
	});

	it('keeps a not group at exactly one child', () => {
		let q = addGroup(emptyQuery(), [], 'not');
		q = addCondition(q, [0], fav);
		expect(addCondition(q, [0], text)).toBe(q);
		expect(addGroup(q, [0], 'or')).toBe(q);
		expect(q.where).toEqual({ op: 'and', children: [{ op: 'not', children: [fav] }] });
	});

	it('refuses a second child in a root not group', () => {
		const root: Query = { v: 1, where: { op: 'not', children: [fav] }, sort: [] };
		expect(addCondition(root, [], text)).toBe(root);
	});

	it('counts conditions across nested groups', () => {
		const q: Query = {
			v: 1,
			where: {
				op: 'and',
				children: [fav, { op: 'or', children: [text, { op: 'not', children: [fav] }] }]
			},
			sort: []
		};
		expect(countConditions(q)).toBe(3);
		expect(countConditions(emptyQuery())).toBe(0);
	});

	describe('combine', () => {
		it('combines the page basics with the filter as AND', () => {
			const q = combine(addCondition(emptyQuery(), [], fav), { type: 'film', q: 'ali' });
			expect(q.where).toEqual({
				op: 'and',
				children: [fav, { kind: 'type', in: ['film'] }, { kind: 'text', q: 'ali' }]
			});
		});

		it('wraps an or filter so its meaning is kept', () => {
			const filter: Query = {
				v: 1,
				where: { op: 'or', children: [fav, text] },
				sort: []
			};
			expect(combine(filter, { favourite: true }).where).toEqual({
				op: 'and',
				children: [{ op: 'or', children: [fav, text] }, fav]
			});
		});

		it('adds the favourite basic', () => {
			expect(combine(emptyQuery(), { favourite: true }).where).toEqual({
				op: 'and',
				children: [fav]
			});
			expect(combine(emptyQuery(), { favourite: false }).where).toBeNull();
		});

		it('with no filter and no basics stays empty', () => {
			expect(combine(emptyQuery(), {}).where).toBeNull();
			expect(combine(emptyQuery(), { type: null, q: '   ' }).where).toBeNull();
		});

		it('returns the filter alone when there are no basics', () => {
			const q = addCondition(emptyQuery(), [], fav);
			expect(combine(q, {}).where).toEqual(q.where);
		});

		it('trims the text', () => {
			expect(combine(emptyQuery(), { q: '  ali  ' }).where).toEqual({
				op: 'and',
				children: [{ kind: 'text', q: 'ali' }]
			});
		});

		it('leaves out text over 200 characters rather than truncating', () => {
			expect(combine(emptyQuery(), { q: 'a'.repeat(200) }).where).not.toBeNull();
			expect(combine(emptyQuery(), { q: 'a'.repeat(201) }).where).toBeNull();
		});

		it('keeps the sort', () => {
			const q: Query = { v: 1, where: null, sort: [{ by: 'name', dir: 'desc' }] };
			expect(combine(q, { type: 'film' }).sort).toEqual([{ by: 'name', dir: 'desc' }]);
		});

		it('does not deepen an and filter that is already at the nesting limit', () => {
			const deep: Query = {
				v: 1,
				where: {
					op: 'and',
					children: [
						{
							op: 'and',
							children: [{ op: 'and', children: [{ op: 'and', children: [fav] }] }]
						}
					]
				},
				sort: []
			};
			const depth = (group: Group): number =>
				1 + Math.max(0, ...group.children.map((c) => (isGroup(c) ? depth(c) : 0)));
			const combined = combine(deep, { type: 'film' });
			expect(depth(combined.where!)).toBeLessThanOrEqual(4);
		});
	});
});

describe('search text length', () => {
	// The server counts characters (code points), not UTF-16 units; each emoji is two units.
	const emoji = (n: number) => '🎬'.repeat(n);

	it('counts emoji as one character each', () => {
		expect(searchTextTooLong(emoji(200))).toBe(false);
		expect(searchTextTooLong(emoji(201))).toBe(true);
		expect(pageConditions({ q: emoji(200) })).toEqual([{ kind: 'text', q: emoji(200) }]);
		expect(pageConditions({ q: emoji(201) })).toEqual([]);
	});

	it('keeps the 200-character limit for plain text', () => {
		expect(searchTextTooLong('a'.repeat(200))).toBe(false);
		expect(searchTextTooLong('a'.repeat(201))).toBe(true);
		expect(pageConditions({ q: 'a'.repeat(201) })).toEqual([]);
	});

	it('counts a type slug in characters too', () => {
		expect(pageConditions({ type: emoji(200) })).toEqual([{ kind: 'type', in: [emoji(200)] }]);
		expect(pageConditions({ type: emoji(201) })).toEqual([]);
	});
});
