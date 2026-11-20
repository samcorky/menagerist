import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	chosenCollections,
	homeCollectionIds,
	homeCollectionQuery,
	toggleHomeCollection
} from '$lib/home-collections';

beforeEach(() => {
	const data = new Map<string, string>();
	vi.stubGlobal('localStorage', {
		getItem: (key: string) => data.get(key) ?? null,
		setItem: (key: string, value: string) => void data.set(key, value)
	});
});

afterEach(() => vi.unstubAllGlobals());

describe('collections chosen for Home', () => {
	it('adds a collection last and takes it off again', () => {
		expect(toggleHomeCollection('a')).toBe(true);
		expect(toggleHomeCollection('b')).toBe(true);
		expect(homeCollectionIds()).toEqual(['a', 'b']);
		expect(toggleHomeCollection('a')).toBe(false);
		expect(homeCollectionIds()).toEqual(['b']);
	});

	it('keeps the chosen order and skips collections that no longer exist', () => {
		const shelves = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
		expect(chosenCollections(['c', 'gone', 'a'], shelves)).toEqual([{ id: 'c' }, { id: 'a' }]);
	});

	it('asks for the newest items of the collection, whatever its kind', () => {
		expect(homeCollectionQuery('a')).toEqual({
			v: 1,
			where: { op: 'and', children: [{ kind: 'collection', mode: 'any', in: ['a'] }] },
			sort: [{ by: 'created', dir: 'desc' }]
		});
	});
});
