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
	directional: true,
	holder: 'source'
} as EdgeTypeResponse;
const locatedIn = {
	slug: 'located-in',
	label: 'Located in',
	reverse_label: 'Contains',
	directional: true,
	holder: 'target'
} as EdgeTypeResponse;
const publishedBy = {
	slug: 'published-by',
	label: 'Published by',
	reverse_label: 'Published',
	directional: true,
	holder: 'none'
} as EdgeTypeResponse;
const shelf = {
	slug: 'shelved-on',
	label: 'Shelved on',
	reverse_label: null,
	directional: true,
	holder: 'target'
} as EdgeTypeResponse;
const kit = {
	slug: 'kit-has',
	label: 'Has',
	reverse_label: null,
	directional: true,
	holder: 'source'
} as EdgeTypeResponse;

const edge = (source: string, target: string, type: string) =>
	({
		id: `${source}-${target}-${type}`,
		source_id: source,
		target_id: target,
		type
	}) as EdgeResponse;

describe('reachChoices', () => {
	it('with the source holding: a holder reads Contains and a held item Inside', () => {
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

	it('with the target holding: the box holds the game that is Located in it', () => {
		const edges = [edge('game', 'box', 'located-in'), edge('box', 'room', 'located-in')];

		expect(reachChoices('box', edges, [locatedIn])).toEqual({
			contents: [{ slug: 'located-in', label: 'Contains' }],
			inside: [{ slug: 'located-in', label: 'Located in' }]
		});
		expect(reachChoices('game', edges, [locatedIn])).toEqual({
			contents: [],
			inside: [{ slug: 'located-in', label: 'Located in' }]
		});
	});

	it('falls back to the label when there is no reverse label', () => {
		const edges = [edge('book', 'me', 'shelved-on')];
		expect(reachChoices('me', edges, [shelf]).contents).toEqual([
			{ slug: 'shelved-on', label: 'Shelved on' }
		]);
	});

	it('ignores relationships that hold nothing and ones it does not know', () => {
		const edges = [edge('me', 'x', 'published-by'), edge('me', 'y', 'mystery')];
		expect(reachChoices('me', edges, [publishedBy])).toEqual({ contents: [], inside: [] });
	});

	it('lists each relationship once, in the order first seen', () => {
		const edges = [
			edge('me', 'a', 'kit-has'),
			edge('me', 'b', 'contains'),
			edge('me', 'c', 'kit-has')
		];
		expect(reachChoices('me', edges, [contains, kit]).contents.map((c) => c.slug)).toEqual([
			'kit-has',
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
