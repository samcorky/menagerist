import { describe, it, expect } from 'vitest';
import {
	GROUP_CAPS,
	PAGES,
	matchRank,
	rankByName,
	matchPages,
	matchItemTypes
} from '../src/lib/palette-search';

describe('GROUP_CAPS', () => {
	it('caps each group', () => {
		expect(GROUP_CAPS).toEqual({ items: 5, collections: 3, itemTypes: 3, pages: 4 });
	});
});

describe('matchRank', () => {
	it('orders exact, prefix, word prefix, other', () => {
		expect(matchRank('Film', 'film')).toBe(0);
		expect(matchRank('Filmography', 'film')).toBe(1);
		expect(matchRank('Short film', 'film')).toBe(2);
		expect(matchRank('Telefilm', 'film')).toBe(3);
	});
	it('ignores case and surrounding whitespace in the query', () => {
		expect(matchRank('FILM', '  fILm ')).toBe(0);
	});
	it('treats non-letters and digits as word breaks', () => {
		expect(matchRank('Sci-fi film', 'fi')).toBe(2);
		expect(matchRank('a_b2c', 'b2')).toBe(2);
	});
});

describe('rankByName', () => {
	it('sorts by rank and keeps input order for ties', () => {
		const rows = [
			{ n: 'Telefilm' },
			{ n: 'Film b' },
			{ n: 'Short film' },
			{ n: 'Film a' },
			{ n: 'film' }
		];
		expect(rankByName(rows, 'film', (r) => r.n).map((r) => r.n)).toEqual([
			'film',
			'Film b',
			'Film a',
			'Short film',
			'Telefilm'
		]);
	});
	it('does not mutate the input', () => {
		const rows = ['b film', 'film'];
		rankByName(rows, 'film', (r) => r);
		expect(rows).toEqual(['b film', 'film']);
	});
});

describe('PAGES', () => {
	it('lists the app pages', () => {
		expect(PAGES.map((p) => p.path)).toEqual([
			'/',
			'/items',
			'/collections',
			'/explore',
			'/settings',
			'/settings/item-types',
			'/settings/relationships',
			'/settings/saved-fields',
			'/settings/examples',
			'/status'
		]);
	});
});

describe('matchPages', () => {
	it('matches on label', () => {
		expect(matchPages('explo')).toEqual([{ label: 'Explore', path: '/explore' }]);
	});
	it('matches on keyword', () => {
		expect(matchPages('connections').map((p) => p.label)).toEqual(['Relationships']);
	});
	it('yields nothing for an empty query', () => {
		expect(matchPages('')).toEqual([]);
		expect(matchPages('   ')).toEqual([]);
	});
	it('ranks and caps results', () => {
		const result = matchPages('s');
		expect(result.length).toBeLessThanOrEqual(GROUP_CAPS.pages);
		expect(result.length).toBe(GROUP_CAPS.pages);
		expect(result[0].label).toBe('Settings');
	});
	it('treats regex characters literally', () => {
		expect(matchPages('(')).toEqual([]);
		expect(matchPages('*')).toEqual([]);
	});
});

describe('matchItemTypes', () => {
	const types = [
		{ label: 'Board game', slug: 'board-game' },
		{ label: 'Film', slug: 'film' },
		{ label: 'Short film', slug: 'short-film' },
		{ label: 'Telefilm', slug: 'tv' },
		{ label: 'Album', slug: 'album' },
		{ label: 'Movie', slug: 'film-extra' }
	];
	it('matches label or slug, ranked by label', () => {
		expect(matchItemTypes(types, 'film').map((t) => t.label)).toEqual([
			'Film',
			'Short film',
			'Telefilm'
		]);
	});
	it('matches on slug alone', () => {
		expect(matchItemTypes(types, 'extra').map((t) => t.label)).toEqual(['Movie']);
	});
	it('yields nothing for an empty query', () => {
		expect(matchItemTypes(types, ' ')).toEqual([]);
	});
	it('caps results and matches regex characters literally', () => {
		expect(matchItemTypes(types, 'm')).toHaveLength(GROUP_CAPS.itemTypes);
		expect(matchItemTypes(types, '(')).toEqual([]);
		expect(matchItemTypes(types, '.*')).toEqual([]);
	});
});
