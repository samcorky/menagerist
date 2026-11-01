import { describe, expect, it } from 'vitest';
import {
	MAX_CONDITIONS,
	MAX_DEPTH,
	MAX_SORT_KEYS,
	MAX_TEXT_LENGTH,
	canAddCondition,
	canAddGroup,
	fitsLimits,
	groupDepthAt
} from '$lib/query/limits';
import { combine } from '$lib/query/tree';
import type { Condition, Group, Node, Query } from '$lib/query/types';

const fav: Condition = { kind: 'favourite', value: true };
const q = (where: Group | null): Query => ({ v: 1, where, sort: [] });
const many = (n: number): Node[] => Array.from({ length: n }, () => fav);

/** A chain of groups nested `depth` levels deep (root counts as 1). */
function nested(depth: number, op: 'and' | 'or' = 'and'): Group {
	let g: Group = { op, children: [fav] };
	for (let i = 1; i < depth; i++) g = { op, children: [g] };
	return g;
}

describe('constants', () => {
	it('mirror the server', () => {
		expect([MAX_CONDITIONS, MAX_DEPTH, MAX_SORT_KEYS, MAX_TEXT_LENGTH]).toEqual([50, 4, 3, 200]);
	});
});

describe('groupDepthAt', () => {
	it('counts the root as 1', () => {
		expect(groupDepthAt([])).toBe(1);
		expect(groupDepthAt([0])).toBe(2);
		expect(groupDepthAt([0, 0])).toBe(3);
	});
	it('treats an empty query as the root', () => {
		expect(groupDepthAt([])).toBe(1);
	});
	it('returns the path length plus one even for a missing path', () => {
		expect(groupDepthAt([5, 5])).toBe(3);
	});
});

describe('canAddCondition', () => {
	it('is false at the limit', () => {
		expect(canAddCondition(q({ op: 'and', children: many(MAX_CONDITIONS - 1) }))).toBe(true);
		expect(canAddCondition(q({ op: 'and', children: many(MAX_CONDITIONS) }))).toBe(false);
		expect(canAddCondition(q(null))).toBe(true);
	});
	it('counts conditions inside nested groups', () => {
		const where: Group = {
			op: 'and',
			children: [{ op: 'or', children: many(MAX_CONDITIONS) }]
		};
		expect(canAddCondition(q(where))).toBe(false);
	});
});

describe('canAddGroup', () => {
	it('allows a group while the new one stays within the depth limit', () => {
		expect(canAddGroup(q(null), [])).toBe(true);
		expect(canAddGroup(q(nested(3)), [])).toBe(true);
		expect(canAddGroup(q(nested(3)), [0, 0])).toBe(true);
		expect(canAddGroup(q(nested(MAX_DEPTH)), [0, 0, 0])).toBe(false);
	});
	it('is false at the deepest group', () => {
		expect(canAddGroup(q(nested(MAX_DEPTH)), [0, 0, 0])).toBe(false);
		expect(canAddGroup(q(nested(MAX_DEPTH)), [0, 0])).toBe(true);
	});
});

describe('fitsLimits', () => {
	it('accepts queries at the limits', () => {
		expect(fitsLimits(q(null))).toBe(true);
		expect(fitsLimits(q(nested(MAX_DEPTH)))).toBe(true);
		expect(fitsLimits(q({ op: 'and', children: many(MAX_CONDITIONS) }))).toBe(true);
	});
	it('rejects too deep or too many', () => {
		expect(fitsLimits(q(nested(MAX_DEPTH + 1)))).toBe(false);
		expect(fitsLimits(q({ op: 'and', children: many(MAX_CONDITIONS + 1) }))).toBe(false);
	});
	it('catches combine() outputs that exceed the limits', () => {
		const deepOr = q(nested(MAX_DEPTH, 'or'));
		expect(fitsLimits(combine(deepOr, { type: 'film' }))).toBe(false);
		const full = q({ op: 'and', children: many(MAX_CONDITIONS) });
		expect(fitsLimits(combine(full, { type: 'film' }))).toBe(false);
		expect(fitsLimits(combine(full, {}))).toBe(true);
		expect(fitsLimits(combine(q({ op: 'and', children: many(3) }), { type: 'film' }))).toBe(true);
	});
});
