import { describe, expect, it } from 'vitest';
import {
	CONTENTS_PAGE_SIZE,
	mayHaveMore,
	pickChoice,
	reachChoices,
	type ReachChoice
} from '$lib/item-reach';
import type { EdgeResponse, EdgeTypeResponse } from '$lib/api/client';

const contains = {
	slug: 'contains',
	label: 'Contains',
	reverse_label: 'Inside',
	directional: true
} as EdgeTypeResponse;
const sibling = {
	slug: 'sibling',
	label: 'Sibling of',
	reverse_label: null,
	directional: false
} as EdgeTypeResponse;
const shelf = {
	slug: 'shelved-on',
	label: 'Shelved on',
	reverse_label: null,
	directional: true
} as EdgeTypeResponse;

const edge = (source: string, target: string, type: string) =>
	({
		id: `${source}-${target}-${type}`,
		source_id: source,
		target_id: target,
		type
	}) as EdgeResponse;

describe('reachChoices', () => {
	it('reads a holder as Contains and a held item as Inside', () => {
		const edges = [edge('shed', 'box', 'contains'), edge('box', 'bag', 'contains')];

		expect(reachChoices('box', edges, [contains])).toEqual({
			contents: [{ slug: 'contains', label: 'Contains' }],
			inside: [{ slug: 'contains', label: 'Inside' }]
		});
		expect(reachChoices('shed', edges, [contains])).toEqual({
			contents: [{ slug: 'contains', label: 'Contains' }],
			inside: []
		});
		expect(reachChoices('bag', edges, [contains]).contents).toEqual([]);
	});

	it('falls back to the label when there is no reverse label', () => {
		const edges = [edge('a', 'me', 'shelved-on')];
		expect(reachChoices('me', edges, [shelf]).inside).toEqual([
			{ slug: 'shelved-on', label: 'Shelved on' }
		]);
	});

	it('ignores relationships with no direction and ones it does not know', () => {
		const edges = [edge('me', 'x', 'sibling'), edge('me', 'y', 'mystery')];
		expect(reachChoices('me', edges, [sibling])).toEqual({ contents: [], inside: [] });
	});

	it('lists each relationship once, in the order first seen', () => {
		const edges = [
			edge('me', 'a', 'shelved-on'),
			edge('me', 'b', 'contains'),
			edge('me', 'c', 'shelved-on')
		];
		expect(reachChoices('me', edges, [contains, shelf]).contents.map((c) => c.slug)).toEqual([
			'shelved-on',
			'contains'
		]);
	});
});

describe('pickChoice', () => {
	const choices: ReachChoice[] = [
		{ slug: 'a', label: 'A' },
		{ slug: 'b', label: 'B' }
	];

	it('keeps the pick while it is offered and falls back to the first', () => {
		expect(pickChoice(choices, 'b')?.slug).toBe('b');
		expect(pickChoice(choices, 'gone')?.slug).toBe('a');
		expect(pickChoice([], 'a')).toBeNull();
	});
});

describe('mayHaveMore', () => {
	it('takes a full page to mean there may be another', () => {
		expect(mayHaveMore(new Array(CONTENTS_PAGE_SIZE).fill(0))).toBe(true);
		expect(mayHaveMore(new Array(CONTENTS_PAGE_SIZE - 1).fill(0))).toBe(false);
		expect(mayHaveMore([])).toBe(false);
	});
});
