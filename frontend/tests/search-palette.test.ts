import { describe, it, expect } from 'vitest';
import {
	SEARCH_RESULT_LIMIT,
	seeAllSearch,
	normaliseQuery,
	liveMessage,
	MAX_QUERY_LENGTH,
	resultSubtitle,
	paletteView,
	defaultHighlight,
	firstLiveValue
} from '../src/lib/search-palette';

describe('normaliseQuery', () => {
	it('trims and handles missing values', () => {
		expect(normaliseQuery('  blue ')).toBe('blue');
		expect(normaliseQuery(null)).toBe('');
		expect(normaliseQuery('   ')).toBe('');
	});
	it('caps the length', () => {
		expect(normaliseQuery('a'.repeat(500))).toHaveLength(MAX_QUERY_LENGTH);
	});
});

describe('seeAllSearch', () => {
	it('sends the trimmed query', () => {
		expect(seeAllSearch('  blue  ')).toBe('q=blue');
	});
	it('encodes reserved characters', () => {
		expect(seeAllSearch('a&b c#d%e')).toBe('q=a%26b+c%23d%25e');
	});
	it('round-trips unicode', () => {
		const search = seeAllSearch('café 日本');
		expect(new URLSearchParams(search).get('q')).toBe('café 日本');
	});
	it('caps long queries', () => {
		const q = new URLSearchParams(seeAllSearch('x'.repeat(1000))).get('q');
		expect(q).toHaveLength(MAX_QUERY_LENGTH);
	});
	it('is an empty value for a blank query', () => {
		expect(seeAllSearch('   ')).toBe('q=');
	});
});

describe('liveMessage', () => {
	const base = { query: 'x', pending: false, showSpinner: false, count: 0, failed: 0 };
	it('says nothing for a blank query', () => {
		expect(liveMessage({ ...base, query: '  ', count: 3 })).toBe('');
	});
	it('says Searching once the spinner shows, whatever has arrived', () => {
		expect(liveMessage({ ...base, pending: true, showSpinner: true })).toBe('Searching…');
		expect(liveMessage({ ...base, pending: true, showSpinner: true, count: 4 })).toBe('Searching…');
		expect(liveMessage({ ...base, pending: true, showSpinner: true, failed: 1 })).toBe(
			'Searching…'
		);
	});
	it('says nothing while pending before the spinner, even with stale counts', () => {
		expect(liveMessage({ ...base, pending: true })).toBe('');
		expect(liveMessage({ ...base, pending: true, count: 5 })).toBe('');
	});
	it('announces the final count once everything has answered', () => {
		expect(liveMessage({ ...base, count: 1 })).toBe('1 result');
		expect(liveMessage({ ...base, count: 6 })).toBe('6 results');
	});
	it('mentions failed groups alongside the count of the others', () => {
		expect(liveMessage({ ...base, count: 3, failed: 1 })).toBe(
			'Some results could not be loaded. 3 results'
		);
		expect(liveMessage({ ...base, count: 1, failed: 2 })).toBe(
			'Some results could not be loaded. 1 result'
		);
	});
	it('reports empty and failed-only outcomes', () => {
		expect(liveMessage({ ...base, query: ' x ' })).toBe('Nothing found for "x"');
		expect(liveMessage({ ...base, failed: 2 })).toBe('Some results could not be loaded');
	});
});

describe('resultSubtitle', () => {
	it('is empty for an untyped item with no match context', () => {
		expect(resultSubtitle(null, null)).toBe('');
	});
	it('shows the type label alone', () => {
		expect(resultSubtitle('Film', null)).toBe('Film');
	});
	it('shows the match context alone', () => {
		expect(resultSubtitle(null, { label: 'Director', text: 'Nolan' })).toBe('Director: Nolan');
	});
	it('joins type and match context', () => {
		expect(resultSubtitle('Film', { label: 'Director', text: 'Nolan' })).toBe(
			'Film · Director: Nolan'
		);
	});
});

describe('paletteView', () => {
	const base = { query: 'x', pending: false, showSpinner: false, count: 0, failed: 0 };
	it('shows the hint for a blank query', () => {
		expect(paletteView({ ...base, query: '   ', count: 3 })).toBe('hint');
	});
	it('stays quiet while a fast load is pending with nothing to show', () => {
		expect(paletteView({ ...base, pending: true })).toBe('idle');
	});
	it('shows the spinner once the load is slow', () => {
		expect(paletteView({ ...base, pending: true, showSpinner: true })).toBe('loading');
	});
	it('keeps earlier results visible while a new load is pending', () => {
		expect(paletteView({ ...base, pending: true, showSpinner: true, count: 2 })).toBe('results');
	});
	it('shows results alongside failed groups', () => {
		expect(paletteView({ ...base, count: 1, failed: 1 })).toBe('results');
	});
	it('shows the retry rows, not Nothing found, when the rest are empty', () => {
		expect(paletteView({ ...base, failed: 1 })).toBe('partial');
	});
	it('waits for pending sources before showing the retry rows', () => {
		expect(paletteView({ ...base, failed: 1, pending: true })).toBe('idle');
	});
	it('shows the empty state only once settled with no results and no failures', () => {
		expect(paletteView(base)).toBe('empty');
	});
	it('shows results once settled', () => {
		expect(paletteView({ ...base, count: 1 })).toBe('results');
	});
});

describe('firstLiveValue', () => {
	it('takes the first row of the first non-empty group', () => {
		expect(
			firstLiveValue([
				{ values: [], stale: false },
				{ values: ['c1', 'c2'], stale: false },
				{ values: ['t1'], stale: false }
			])
		).toBe('c1');
	});
	it('skips groups still holding rows of an earlier query', () => {
		expect(
			firstLiveValue([
				{ values: ['c-old'], stale: true },
				{ values: ['t1'], stale: false }
			])
		).toBe('t1');
	});
	it('is empty when every row is stale or absent', () => {
		expect(firstLiveValue([{ values: ['c-old'], stale: true }])).toBe('');
	});
});

describe('defaultHighlight', () => {
	it('stays on See all until the items group has answered', () => {
		expect(defaultHighlight('page:/', false, 'all')).toBe('all');
	});
	it('moves to the first row once items have answered', () => {
		expect(defaultHighlight('item:1', true, 'all')).toBe('item:1');
	});
	it('falls back to See all when nothing was found', () => {
		expect(defaultHighlight('', true, 'all')).toBe('all');
	});
});

describe('SEARCH_RESULT_LIMIT', () => {
	it('is 8', () => {
		expect(SEARCH_RESULT_LIMIT).toBe(8);
	});
});
