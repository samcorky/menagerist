import { describe, expect, it } from 'vitest';
import { decodeQuery, encodeQuery } from '$lib/query/codec';
import {
	DEPTH_CHOICES,
	canChooseDepth,
	withConnectionDepth,
	withConnectionDirection,
	withConnectionRelationship
} from '$lib/query/builder';
import { describeCondition, type SummaryLookup } from '$lib/query/summary';
import type { Condition, Query } from '$lib/query/types';

const ITEM = '018f5c2e-7b1a-7c3e-9d4f-1a2b3c4d5e6f';
const contains = {
	slug: 'contains',
	label: 'Contains',
	reverse_label: 'Inside',
	directional: true
};
const sibling = { slug: 'sibling', label: 'Sibling of', reverse_label: null, directional: false };

const q = (...children: Condition[]): Query => ({
	v: 1,
	where: { op: 'and', children },
	sort: []
});
const roundTrip = (c: unknown) => decodeQuery(encodeQuery(q(c as Condition)));

const lookup: SummaryLookup = {
	typeLabel: (slug) => slug,
	fieldLabel: (_type, key) => key,
	relationship: (slug) =>
		slug === 'contains' ? { label: 'Contains', reverse_label: 'Inside', directional: true } : null,
	itemName: (id) => (id === ITEM ? 'Casablanca box' : null)
};

describe('connection depth in the codec', () => {
	it.each([1, 3, 25])('keeps a depth of %i', (depth) => {
		const c: Condition = {
			kind: 'connection',
			mode: 'exists',
			relationship: 'contains',
			direction: 'out',
			depth
		};
		expect(roundTrip(c)?.where?.children[0]).toEqual(c);
	});

	it.each<[string, Record<string, unknown>]>([
		['zero', { depth: 0 }],
		['above the cap', { depth: 26 }],
		['a string', { depth: '3' }],
		['a boolean', { depth: true }],
		['a fraction', { depth: 2.5 }],
		['null', { depth: null }],
		['with direction any', { depth: 2, direction: 'any' }],
		['without a relationship', { depth: 2, relationship: undefined }]
	])('rejects a depth that is %s', (_name, extra) => {
		const c = {
			kind: 'connection',
			mode: 'exists',
			relationship: 'contains',
			direction: 'out',
			...extra
		};
		expect(roundTrip(c)).toBeNull();
	});

	it('keeps a depth on an "is connected to" row', () => {
		const c: Condition = {
			kind: 'connection',
			mode: 'to',
			item: ITEM,
			relationship: 'contains',
			direction: 'in',
			depth: 25
		};
		expect(roundTrip(c)?.where?.children[0]).toEqual(c);
	});
});

describe('connection depth in the builder', () => {
	const base: Condition = {
		kind: 'connection',
		mode: 'exists',
		relationship: 'contains',
		direction: 'out'
	};

	it('offers a depth only for a directional relationship with a direction', () => {
		expect(canChooseDepth(base, contains)).toBe(true);
		expect(canChooseDepth({ ...base, direction: undefined } as Condition, contains)).toBe(false);
		expect(canChooseDepth({ ...base, relationship: undefined } as Condition, null)).toBe(false);
		expect(canChooseDepth(base, sibling)).toBe(false);
	});

	it('offers two plain-language choices', () => {
		expect(DEPTH_CHOICES.map((d) => [d.value, d.label])).toEqual([
			[1, 'Directly linked'],
			[25, 'Any depth']
		]);
	});

	it('sets and clears the depth', () => {
		const deep = withConnectionDepth(base, 25);
		expect(deep).toEqual({ ...base, depth: 25 });
		expect(withConnectionDepth(deep, 1)).toEqual(base);
	});

	it('drops the depth when the direction becomes either way', () => {
		const deep = withConnectionDepth(base, 25);
		expect(withConnectionDirection(deep, 'any')).toEqual({
			kind: 'connection',
			mode: 'exists',
			relationship: 'contains'
		});
		expect(withConnectionDirection(deep, 'in')).toEqual({ ...deep, direction: 'in' });
	});

	it('drops the depth when the relationship goes or has no direction', () => {
		const deep = withConnectionDepth(base, 25);
		expect(withConnectionRelationship(deep, null)).not.toHaveProperty('depth');
		expect(withConnectionRelationship(deep, sibling)).not.toHaveProperty('depth');
		expect(withConnectionRelationship(deep, contains)).toHaveProperty('depth', 25);
	});
});

describe('connection depth in the summary', () => {
	it.each<[Condition, string]>([
		[
			{ kind: 'connection', mode: 'exists', relationship: 'contains', direction: 'out', depth: 25 },
			'Has a linked item via Contains from this item, at any depth'
		],
		[
			{ kind: 'connection', mode: 'exists', relationship: 'contains', direction: 'out', depth: 3 },
			'Has a linked item via Contains from this item, up to 3 steps'
		],
		[
			{
				kind: 'connection',
				mode: 'to',
				item: ITEM,
				relationship: 'contains',
				direction: 'in',
				depth: 25
			},
			'Connected to Casablanca box via Inside, at any depth'
		]
	])('reads %#', (c, text) => {
		expect(describeCondition(c, lookup)).toBe(text);
	});

	it('says nothing extra for a direct link', () => {
		const c: Condition = {
			kind: 'connection',
			mode: 'exists',
			relationship: 'contains',
			direction: 'out'
		};
		expect(describeCondition(c, lookup)).toBe('Has a linked item via Contains from this item');
	});
});
