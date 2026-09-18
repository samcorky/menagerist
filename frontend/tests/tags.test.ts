import { describe, it, expect } from 'vitest';
import { normaliseTags } from '../src/lib/tags';

describe('normaliseTags', () => {
	it('trims, lowercases, de-duplicates and drops blanks, keeping order', () => {
		expect(normaliseTags([' Sci-Fi ', 'horror', 'SCI-FI', '  ', ''])).toEqual(['sci-fi', 'horror']);
	});

	it('returns an empty list for no tags', () => {
		expect(normaliseTags([])).toEqual([]);
	});
});
