import { describe, it, expect } from 'vitest';
import {
	SEARCH_RESULT_LIMIT,
	seeAllSearch,
	normaliseQuery,
	liveMessage,
	MAX_QUERY_LENGTH,
	resultSubtitle,
	paletteView
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
	it('announces counts, empty, loading and errors', () => {
		expect(liveMessage('results', 'x', 1, null)).toBe('1 result');
		expect(liveMessage('results', 'x', 5, null)).toBe('5 results');
		expect(liveMessage('empty', ' x ', 0, null)).toBe('No items match "x"');
		expect(liveMessage('loading', 'x', 0, null)).toBe('Searching');
		expect(liveMessage('error', 'x', 0, 'Offline')).toBe('Offline');
		expect(liveMessage('hint', '', 0, null)).toBe('');
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
	const base = { query: 'x', error: false, pending: false, showSpinner: false, count: 0 };
	it('shows the hint for a blank query', () => {
		expect(paletteView({ ...base, query: '   ', count: 3 })).toBe('hint');
	});
	it('shows the error state', () => {
		expect(paletteView({ ...base, error: true })).toBe('error');
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
	it('puts the error ahead of earlier results', () => {
		expect(paletteView({ ...base, error: true, count: 3 })).toBe('error');
	});
	it('shows the empty state once settled with no results', () => {
		expect(paletteView(base)).toBe('empty');
	});
	it('shows results once settled', () => {
		expect(paletteView({ ...base, count: 1 })).toBe('results');
	});
});

describe('SEARCH_RESULT_LIMIT', () => {
	it('is 8', () => {
		expect(SEARCH_RESULT_LIMIT).toBe(8);
	});
});
