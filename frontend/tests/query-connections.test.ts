import { describe, expect, it } from 'vitest';
import { decodeQuery, encodeQuery, parseQuery } from '$lib/query/codec';
import { describeCondition, describeGroup, type SummaryLookup } from '$lib/query/summary';
import {
	applyDraft,
	chipModels,
	conditionNumbers,
	conditionProblem,
	directionChoices,
	groupAt,
	missingFieldMessage,
	relationshipOptionLabel,
	STALE_CONNECTION_MESSAGE,
	withConnectionDirection,
	withConnectionFilter,
	withConnectionMode,
	withConnectionRelationship
} from '$lib/query/builder';
import { canAddGroup, canNestConnection, fitsLimits, groupDepthAt } from '$lib/query/limits';
import { addCondition, addGroup, countConditions, removeAt, replaceAt } from '$lib/query/tree';
import { mapWarnings, parseQueryPath } from '$lib/query/warnings';
import { FAR_END, type Condition, type Group, type Query } from '$lib/query/types';
import { catalogue } from './query-builder-fixtures';

const ITEM = '018f5c2e-7b1a-7c3e-9d4f-1a2b3c4d5e6f';
const fav: Condition = { kind: 'favourite', value: true };

const q = (...children: (Condition | Group)[]): Query => ({
	v: 1,
	where: { op: 'and', children },
	sort: []
});
const farEnd = (...children: (Condition | Group)[]): Group => ({ op: 'and', children });
const roundTrip = (query: unknown) => decodeQuery(encodeQuery(query as Query));

const lookup: SummaryLookup = {
	typeLabel: (slug) => slug,
	fieldLabel: (_type, key) => key,
	relationship: (slug) =>
		slug === 'directed-by'
			? { label: 'Directed by', reverse_label: 'Director of', directional: true }
			: slug === 'sibling-of'
				? { label: 'Sibling of', reverse_label: null, directional: false }
				: null,
	itemName: (id) => (id === ITEM ? 'Casablanca' : null)
};

describe('connection decode and encode', () => {
	it.each<[string, Condition]>([
		['exists', { kind: 'connection', mode: 'exists' }],
		['none', { kind: 'connection', mode: 'none' }],
		[
			'exists with a relationship and direction',
			{ kind: 'connection', mode: 'exists', relationship: 'directed-by', direction: 'out' }
		],
		['to an item', { kind: 'connection', mode: 'to', item: ITEM }],
		[
			'to an item by a relationship',
			{ kind: 'connection', mode: 'to', item: ITEM, relationship: 'directed-by', direction: 'in' }
		],
		[
			'with a far-end filter',
			{ kind: 'connection', mode: 'exists', where: farEnd(fav, { kind: 'text', q: 'x' }) }
		],
		[
			'none with a far-end filter holding a group',
			{
				kind: 'connection',
				mode: 'none',
				where: { op: 'or', children: [fav, { op: 'not', children: [{ kind: 'text', q: 'y' }] }] }
			}
		]
	])('round-trips %s', (_name, condition) => {
		expect(roundTrip(q(condition))).toEqual(q(condition));
	});

	it('accepts null for the optional parts, as the server does', () => {
		const decoded = parseQuery({
			v: 1,
			where: {
				op: 'and',
				children: [
					{ kind: 'connection', mode: 'exists', relationship: null, item: null, where: null }
				]
			},
			sort: []
		});
		expect(decoded?.where?.children[0]).toEqual({ kind: 'connection', mode: 'exists' });
	});

	it.each<[string, unknown]>([
		['unknown mode', { kind: 'connection', mode: 'some' }],
		['no mode', { kind: 'connection' }],
		['unknown direction', { kind: 'connection', mode: 'exists', direction: 'up' }],
		['null direction', { kind: 'connection', mode: 'exists', direction: null }],
		['empty relationship', { kind: 'connection', mode: 'exists', relationship: '' }],
		['numeric relationship', { kind: 'connection', mode: 'exists', relationship: 3 }],
		['to without an item', { kind: 'connection', mode: 'to' }],
		['to with a bad item', { kind: 'connection', mode: 'to', item: 'nope' }],
		['to with a where', { kind: 'connection', mode: 'to', item: ITEM, where: farEnd(fav) }],
		['exists with an item', { kind: 'connection', mode: 'exists', item: ITEM }],
		['none with an item', { kind: 'connection', mode: 'none', item: ITEM }],
		['where is not a group', { kind: 'connection', mode: 'exists', where: fav }],
		['empty where', { kind: 'connection', mode: 'exists', where: { op: 'and', children: [] } }],
		[
			'connection inside the far-end filter',
			{ kind: 'connection', mode: 'exists', where: farEnd({ kind: 'connection', mode: 'exists' }) }
		],
		[
			'connection in a group inside the far-end filter',
			{
				kind: 'connection',
				mode: 'exists',
				where: farEnd({ op: 'or', children: [{ kind: 'connection', mode: 'none' }] })
			}
		],
		[
			'malformed far-end condition',
			{ kind: 'connection', mode: 'exists', where: farEnd({ kind: 'text', q: '' }) }
		]
	])('rejects %s', (_name, condition) => {
		expect(roundTrip(q(condition as Condition))).toBeNull();
	});

	it('counts the far-end filter towards the 50 conditions', () => {
		const many = (n: number) => Array.from({ length: n }, () => fav);
		const withFilter = (n: number) =>
			q({ kind: 'connection', mode: 'exists', where: farEnd(...many(n)) });
		expect(roundTrip(withFilter(49))).not.toBeNull();
		expect(roundTrip(withFilter(50))).toBeNull();
		expect(roundTrip(q(...many(49), { kind: 'connection', mode: 'exists' }))).not.toBeNull();
		expect(
			roundTrip(q(...many(49), { kind: 'connection', mode: 'exists', where: farEnd(fav) }))
		).toBeNull();
	});

	it('measures the far-end filter depth from its own root', () => {
		const nest = (depth: number): Group => {
			let group: Group = { op: 'and', children: [fav] };
			for (let i = 1; i < depth; i++) group = { op: 'and', children: [group] };
			return group;
		};
		// A root at depth 3 holding a filter that is 4 deep is fine: each is measured alone.
		const deepEnd = q({ kind: 'connection', mode: 'exists', where: nest(4) });
		const deepRoot = { op: 'and', children: [{ op: 'and', children: [deepEnd.where] }] };
		expect(roundTrip(deepEnd)).not.toBeNull();
		expect(roundTrip({ ...deepEnd, where: deepRoot })).not.toBeNull();
		expect(roundTrip(q({ kind: 'connection', mode: 'exists', where: nest(5) }))).toBeNull();
		expect(fitsLimits(deepEnd)).toBe(true);
		expect(fitsLimits(q({ kind: 'connection', mode: 'exists', where: nest(5) }))).toBe(false);
	});
});

describe('countConditions', () => {
	it('includes the connection and its far-end filter', () => {
		expect(countConditions(q({ kind: 'connection', mode: 'exists' }))).toBe(1);
		expect(
			countConditions(q(fav, { kind: 'connection', mode: 'none', where: farEnd(fav, farEnd(fav)) }))
		).toBe(4);
	});
});

describe('canNestConnection and depth', () => {
	it('is false inside a far-end filter only', () => {
		expect(canNestConnection([])).toBe(true);
		expect(canNestConnection([0, 1])).toBe(true);
		expect(canNestConnection([0, FAR_END])).toBe(false);
		expect(canNestConnection([0, FAR_END, 1])).toBe(false);
	});

	it('restarts the group depth at a far-end filter', () => {
		expect(groupDepthAt([])).toBe(1);
		expect(groupDepthAt([0])).toBe(2);
		expect(groupDepthAt([0, FAR_END])).toBe(1);
		expect(groupDepthAt([0, FAR_END, 2])).toBe(2);
		const query = q({ kind: 'connection', mode: 'exists', where: farEnd(fav) });
		expect(canAddGroup(query, [0, FAR_END])).toBe(true);
		expect(canAddGroup(query, [0, FAR_END, 0, 0, 0])).toBe(false);
	});
});

describe('tree edits through a far-end filter', () => {
	const connection: Condition = {
		kind: 'connection',
		mode: 'exists',
		where: farEnd(fav)
	};

	it('finds the filter group', () => {
		expect(groupAt(q(connection), [0, FAR_END])?.children).toEqual([fav]);
		expect(groupAt(q(fav), [0, FAR_END])).toBeNull();
	});

	it('adds a condition to the filter', () => {
		const next = addCondition(q(connection), [0, FAR_END], { kind: 'text', q: 'a' });
		expect(groupAt(next, [0, FAR_END])?.children).toHaveLength(2);
	});

	it('adds a group to the filter and keeps it until filled', () => {
		const next = addGroup(q(connection), [0, FAR_END], 'or');
		expect(groupAt(next, [0, FAR_END, 1])).toEqual({ op: 'or', children: [] });
	});

	it('replaces a row in the filter', () => {
		const next = replaceAt(q(connection), [0, FAR_END, 0], { kind: 'text', q: 'z' });
		expect(groupAt(next, [0, FAR_END])?.children).toEqual([{ kind: 'text', q: 'z' }]);
	});

	it('removing the last filter row removes the filter, not the connection', () => {
		const next = removeAt(q(connection), [0, FAR_END, 0]);
		expect(next.where?.children).toEqual([{ kind: 'connection', mode: 'exists' }]);
	});

	it('removing the filter keeps the connection', () => {
		const next = removeAt(q(connection), [0, FAR_END]);
		expect(next.where?.children).toEqual([{ kind: 'connection', mode: 'exists' }]);
	});

	it('leaves the query alone for a path that leads nowhere', () => {
		const query = q(fav);
		expect(removeAt(query, [0, FAR_END, 0])).toBe(query);
		expect(addCondition(query, [0, FAR_END], fav)).toBe(query);
	});

	it('numbers the filter rows after their connection', () => {
		const numbers = conditionNumbers(q(connection, fav));
		expect(Object.fromEntries(numbers)).toEqual({ '0': 1, '0.-1.0': 2, '1': 3 });
	});
});

describe('builder edits', () => {
	const directed = {
		slug: 'directed-by',
		label: 'Directed by',
		reverse_label: 'Director of',
		directional: true
	};
	const sibling = {
		slug: 'sibling-of',
		label: 'Sibling of',
		reverse_label: null,
		directional: false
	};

	it('drops the filter when switching to "is connected to", and the item when leaving it', () => {
		const withFilter: Condition = { kind: 'connection', mode: 'exists', where: farEnd(fav) };
		expect(withConnectionMode(withFilter, 'to')).toEqual({ kind: 'connection', mode: 'to' });
		const to: Condition = { kind: 'connection', mode: 'to', item: ITEM };
		expect(withConnectionMode(to, 'none')).toEqual({ kind: 'connection', mode: 'none' });
		expect(withConnectionMode(withFilter, 'none')).toEqual({
			kind: 'connection',
			mode: 'none',
			where: farEnd(fav)
		});
	});

	it('a non-directional relationship loses the direction', () => {
		const c: Condition = { kind: 'connection', mode: 'exists', direction: 'out' };
		expect(withConnectionRelationship(c, sibling)).toEqual({
			kind: 'connection',
			mode: 'exists',
			relationship: 'sibling-of'
		});
		expect(withConnectionRelationship(c, directed)).toEqual({
			kind: 'connection',
			mode: 'exists',
			relationship: 'directed-by',
			direction: 'out'
		});
		expect(withConnectionRelationship({ ...c, relationship: 'x' }, null)).toEqual({
			kind: 'connection',
			mode: 'exists',
			direction: 'out'
		});
	});

	it('"either way" leaves the direction out', () => {
		const c: Condition = { kind: 'connection', mode: 'exists', direction: 'in' };
		expect(withConnectionDirection(c, 'any')).toEqual({ kind: 'connection', mode: 'exists' });
		expect(withConnectionDirection(c, 'out')).toEqual({
			kind: 'connection',
			mode: 'exists',
			direction: 'out'
		});
	});

	it('starts and drops the far-end filter', () => {
		const c: Condition = { kind: 'connection', mode: 'exists' };
		const started = withConnectionFilter(c, true);
		expect(started).toMatchObject({ where: { op: 'and' } });
		expect(withConnectionFilter(started, false)).toEqual(c);
	});

	it('offers directions only for directional relationships', () => {
		expect(directionChoices(sibling)).toEqual([]);
		expect(directionChoices(directed).map((d) => d.value)).toEqual(['any', 'out', 'in']);
		expect(directionChoices(null).map((d) => d.value)).toEqual(['any', 'out', 'in']);
		expect(directionChoices(directed).map((d) => d.label)).toEqual([
			'Either way',
			'From this item',
			'To this item'
		]);
		expect(relationshipOptionLabel(directed)).toBe('Directed by / Director of');
		expect(relationshipOptionLabel(sibling)).toBe('Sibling of');
	});

	it('needs an item for "is connected to"', () => {
		expect(conditionProblem({ kind: 'connection', mode: 'to' }, catalogue)).toBe('Choose an item.');
		expect(conditionProblem({ kind: 'connection', mode: 'to', item: ITEM }, catalogue)).toBeNull();
		expect(conditionProblem({ kind: 'connection', mode: 'exists' }, catalogue)).toBeNull();
	});

	it('applyDraft drops unfinished far-end rows but keeps the connection', () => {
		const blank: Condition = { kind: 'field', type: '', key: '', op: '' };
		const draft = q({ kind: 'connection', mode: 'exists', where: farEnd(blank) });
		const { query } = applyDraft(draft, catalogue);
		expect(query.where?.children).toEqual([{ kind: 'connection', mode: 'exists' }]);
	});

	it('applyDraft keeps finished far-end rows and maps their paths', () => {
		const blank: Condition = { kind: 'field', type: '', key: '', op: '' };
		const draft = q({ kind: 'connection', mode: 'exists', where: farEnd(blank, fav) });
		const { query, toApplied } = applyDraft(draft, catalogue);
		expect(query.where?.children[0]).toMatchObject({ where: { children: [fav] } });
		expect(toApplied.get('0.-1.1')).toBe('0.-1.0');
	});

	it('applyDraft drops an unfinished "is connected to"', () => {
		const { query } = applyDraft(q({ kind: 'connection', mode: 'to' }), catalogue);
		expect(query.where).toBeNull();
	});
});

describe('summaries', () => {
	it.each<[Condition, string]>([
		[{ kind: 'connection', mode: 'exists' }, 'Has a linked item'],
		[{ kind: 'connection', mode: 'none' }, 'Has no linked item'],
		[
			{ kind: 'connection', mode: 'exists', relationship: 'directed-by' },
			'Has a linked item via Directed by'
		],
		[
			{ kind: 'connection', mode: 'none', relationship: 'directed-by', direction: 'in' },
			'Has no linked item via Director of'
		],
		[
			{ kind: 'connection', mode: 'exists', relationship: 'directed-by', direction: 'out' },
			'Has a linked item via Directed by from this item'
		],
		[
			{ kind: 'connection', mode: 'exists', relationship: 'sibling-of', direction: 'out' },
			'Has a linked item via Sibling of'
		],
		[{ kind: 'connection', mode: 'exists', direction: 'in' }, 'Has a linked item to this item'],
		[{ kind: 'connection', mode: 'to', item: ITEM }, 'Connected to Casablanca'],
		[
			{ kind: 'connection', mode: 'to', item: ITEM, relationship: 'directed-by' },
			'Connected to Casablanca via Directed by'
		],
		[
			{ kind: 'connection', mode: 'to', item: '018f5c2e-7b1a-7c3e-9d4f-1a2b3c4d5e70' },
			'Connected to an item that no longer exists'
		],
		[
			{ kind: 'connection', mode: 'exists', relationship: 'gone' },
			'Has a linked item via a relationship that no longer exists'
		],
		[
			{ kind: 'connection', mode: 'exists', where: farEnd({ kind: 'text', q: 'x' }) },
			'Has a linked item where Contains “x”'
		],
		[
			{
				kind: 'connection',
				mode: 'none',
				where: { op: 'or', children: [fav, { kind: 'text', q: 'x' }] }
			},
			'Has no linked item where Any of: Is a favourite; Contains “x”'
		]
	])('%j', (condition, text) => {
		expect(describeCondition(condition, lookup)).toBe(text);
	});

	it('says what it can while names are still loading', () => {
		const loading: SummaryLookup = { typeLabel: (s) => s, fieldLabel: (_t, k) => k };
		expect(describeCondition({ kind: 'connection', mode: 'to', item: ITEM }, loading)).toBe(
			'Connected to an item'
		);
		expect(
			describeCondition({ kind: 'connection', mode: 'exists', relationship: 'x' }, loading)
		).toBe('Has a linked item via a relationship');
	});

	it('describes a group on one line', () => {
		expect(describeGroup(farEnd(fav), lookup)).toBe('Is a favourite');
		expect(describeGroup({ op: 'not', children: [fav] }, lookup)).toBe('Not: Is a favourite');
	});
});

describe('warnings', () => {
	it.each([
		['where.children[1].where', { where: [1, FAR_END] }],
		['where.children[1].where.children[0]', { where: [1, FAR_END, 0] }],
		['where.children[2].where.children[1].children[0]', { where: [2, FAR_END, 1, 0] }],
		// a collection row inside the filter, and a rule of the smart collection it inlines
		['where.children[0].where.children[1].in[0]', { where: [0, FAR_END, 1] }],
		['where.children[0].where.children[1].in[0].children[2]', { where: [0, FAR_END, 1] }],
		// a connection inside an inlined smart collection belongs to the collection row
		['where.children[0].in[0].children[1].where.children[0]', { where: [0] }]
	])('parses %s', (path, expected) => {
		expect(parseQueryPath(path)).toEqual(expected);
	});

	it('ignores a malformed far-end path', () => {
		expect(parseQueryPath('where.children[0].where[0]')).toBeNull();
		expect(parseQueryPath('where.children[0].wheres')).toBeNull();
	});

	it('maps a far-end warning to its row path key and keeps the server text', () => {
		const marks = mapWarnings([
			{ path: 'where.children[1]', message: "The relationship 'x' no longer exists." },
			{ path: 'where.children[1].where.children[0]', message: 'This field no longer exists.' }
		]);
		expect([...marks.conditions]).toEqual(['1', '1.-1.0']);
		expect(marks.messages.get('1')).toBe("The relationship 'x' no longer exists.");
	});

	it('strips the page prefix from a far-end path', () => {
		const marks = mapWarnings([{ path: 'where.children[0].children[2].where.children[0]' }], [0]);
		expect([...marks.conditions]).toEqual(['2.-1.0']);
	});
});

describe('chips', () => {
	const query = q({
		kind: 'connection',
		mode: 'exists',
		relationship: 'directed-by',
		where: farEnd(fav)
	});

	it('shows one chip for the connection, with its filter in the text', () => {
		const { chips } = chipModels(query, lookup);
		expect(chips).toHaveLength(1);
		expect(chips[0].text).toBe('Has a linked item via Directed by where Is a favourite');
		expect(chips[0].warning).toBe(false);
	});

	it('flags the chip for a warning inside the filter', () => {
		const { chips } = chipModels(query, lookup, new Set(['0.-1.0']));
		expect(chips[0].warning).toBe(true);
	});

	it('uses the server text for a flagged connection, else the fixed one', () => {
		const flagged = new Set(['0']);
		expect(chipModels(query, lookup, flagged, new Map([['0', 'Gone.']])).chips[0].message).toBe(
			'Gone.'
		);
		expect(chipModels(query, lookup, flagged).chips[0].message).toBe(STALE_CONNECTION_MESSAGE);
		expect(missingFieldMessage({ kind: 'connection', mode: 'exists' })).toBe(
			STALE_CONNECTION_MESSAGE
		);
	});

	it('keeps a connection in a nested group as one chip', () => {
		const nested = q({
			op: 'or',
			children: [fav, { kind: 'connection', mode: 'none' }]
		});
		expect(chipModels(nested, lookup).chips[0].text).toBe(
			'Any of: Is a favourite; Has no linked item'
		);
	});
});
