import { describe, expect, it } from 'vitest';
import type { EdgeTypeResponse } from '$lib/api/client';
import { allowsItemType, describeLimits, fitsLimits, parentsByType } from '$lib/connection-limits';

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

describe('limits and subtypes', () => {
	const parents = parentsByType([
		{ slug: 'memorabilia', parent: null },
		{ slug: 'poster', parent: 'memorabilia' },
		{ slug: 'figure', parent: 'memorabilia' },
		{ slug: 'box' }
	]);

	it('maps each subtype to its parent and leaves out the rest', () => {
		expect([...parents]).toEqual([
			['poster', 'memorabilia'],
			['figure', 'memorabilia']
		]);
	});

	it('lets a limit on a parent cover its subtypes and itself', () => {
		expect(allowsItemType(['memorabilia'], 'poster', parents)).toBe(true);
		expect(allowsItemType(['memorabilia'], 'figure', parents)).toBe(true);
		expect(allowsItemType(['memorabilia'], 'memorabilia', parents)).toBe(true);
		expect(allowsItemType(['memorabilia'], 'box', parents)).toBe(false);
	});

	it('lets a limit on a subtype cover only that subtype', () => {
		expect(allowsItemType(['poster'], 'poster', parents)).toBe(true);
		expect(allowsItemType(['poster'], 'memorabilia', parents)).toBe(false);
		expect(allowsItemType(['poster'], 'figure', parents)).toBe(false);
	});

	it('still refuses an untyped item, and ignores the parents when none are given', () => {
		expect(allowsItemType(['memorabilia'], null, parents)).toBe(false);
		expect(allowsItemType(['memorabilia'], 'poster')).toBe(false);
	});

	it('checks both ends of a connection type through the parents', () => {
		const storedIn = limits(['box'], ['memorabilia']);
		expect(fitsLimits(storedIn, 'box', 'poster', parents)).toBe(true);
		expect(fitsLimits(storedIn, 'poster', 'poster', parents)).toBe(false);
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
