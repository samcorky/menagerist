import { describe, expect, it } from 'vitest';
import type { EdgeTypeResponse } from '$lib/api/client';
import { allowsItemType, describeLimits, fitsLimits } from '$lib/connection-limits';

const limits = (source_types: string[], target_types: string[]) =>
	({ source_types, target_types }) as EdgeTypeResponse;

describe('allowsItemType', () => {
	it('allows anything, untyped included, with no limit', () => {
		expect(allowsItemType([], 'book')).toBe(true);
		expect(allowsItemType([], null)).toBe(true);
		expect(allowsItemType(undefined, undefined)).toBe(true);
	});

	it('allows only the listed types, and never an untyped item, under a limit', () => {
		expect(allowsItemType(['book', 'comic'], 'comic')).toBe(true);
		expect(allowsItemType(['book'], 'film')).toBe(false);
		expect(allowsItemType(['book'], null)).toBe(false);
	});
});

describe('fitsLimits', () => {
	const signedBy = limits(['book', 'comic'], ['person']);

	it('checks both ends', () => {
		expect(fitsLimits(signedBy, 'book', 'person')).toBe(true);
		expect(fitsLimits(signedBy, 'film', 'person')).toBe(false);
		expect(fitsLimits(signedBy, 'book', 'book')).toBe(false);
	});

	it('fits an unknown connection type', () => {
		expect(fitsLimits(undefined, 'film', null)).toBe(true);
	});
});

describe('describeLimits', () => {
	it('is null with no limit', () => {
		expect(describeLimits(limits([], []))).toBeNull();
	});

	it('names each end, using "any" for an open one', () => {
		expect(describeLimits(limits(['book', 'comic'], ['person']))).toBe('book, comic → person');
		expect(describeLimits(limits([], ['person']))).toBe('any → person');
		expect(describeLimits(limits(['book'], []))).toBe('book → any');
	});

	it('uses the item types labels when given', () => {
		const labels = new Map([['book', 'Book']]);
		expect(describeLimits(limits(['book'], ['unknown']), labels)).toBe('Book → unknown');
	});
});
