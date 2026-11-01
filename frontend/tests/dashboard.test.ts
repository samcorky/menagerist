import { describe, expect, it } from 'vitest';
import {
	TIDY_LIST_LIMIT,
	editedQuery,
	everythingQuery,
	favouriteQuery,
	greeting,
	itemsHref,
	monthQuery,
	newestQuery,
	noDescriptionQuery,
	noPhotoQuery,
	noTypeQuery,
	notInCollectionQuery,
	percent,
	photoQuery,
	tidyRows
} from '$lib/dashboard';
import { decodeQuery, parseQuery } from '$lib/query/codec';
import { FILTER_PARAM } from '$lib/query/items-page';

const ids = (n: number) =>
	Array.from({ length: n }, (_, i) => `018f5c2e-7b1a-7c3e-9d4f-${String(i).padStart(12, '0')}`);
const slugs = (n: number) => Array.from({ length: n }, (_, i) => `type-${i}`);

describe('dashboard queries', () => {
	it('matches every item, and every favourite', () => {
		expect(everythingQuery()).toEqual({ v: 1, where: null, sort: [] });
		expect(favouriteQuery().where?.children).toEqual([{ kind: 'favourite', value: true }]);
	});

	it('sorts the newest list by creation, latest first', () => {
		expect(newestQuery().sort).toEqual([{ by: 'created', dir: 'desc' }]);
		expect(newestQuery().where).toBeNull();
	});

	it('sorts the recently edited list by update, latest first', () => {
		expect(editedQuery().sort).toEqual([{ by: 'updated', dir: 'desc' }]);
	});

	it('counts items created in the last 30 days', () => {
		expect(monthQuery().where).toEqual({
			op: 'and',
			children: [{ kind: 'date', on: 'created', op: '>=', value: { rel: '-30d' } }]
		});
	});

	it('finds items with and without a photo', () => {
		expect(photoQuery().where?.children).toEqual([{ kind: 'media', mode: 'has' }]);
		expect(noPhotoQuery().where?.children).toEqual([{ kind: 'media', mode: 'none' }]);
	});

	it('finds items with no description', () => {
		expect(noDescriptionQuery().where?.children).toEqual([{ kind: 'description', op: 'empty' }]);
	});

	it('every query is one the server accepts', () => {
		for (const query of [
			newestQuery(),
			everythingQuery(),
			favouriteQuery(),
			editedQuery(),
			monthQuery(),
			photoQuery(),
			noPhotoQuery(),
			noDescriptionQuery(),
			notInCollectionQuery(ids(3)),
			noTypeQuery(['film', 'book'])
		]) {
			expect(parseQuery(JSON.parse(JSON.stringify(query)))).not.toBeNull();
		}
	});
});

describe('queries that list ids', () => {
	it('finds items in none of the collections', () => {
		expect(notInCollectionQuery(ids(2))?.where?.children).toEqual([
			{ kind: 'collection', mode: 'none', in: ids(2) }
		]);
	});

	it('finds items whose type is none of the types', () => {
		expect(noTypeQuery(['film'])?.where?.children).toEqual([
			{ op: 'not', children: [{ kind: 'type', in: ['film'] }] }
		]);
	});

	it('is left out with nothing to list or more ids than the server allows', () => {
		expect(notInCollectionQuery([])).toBeNull();
		expect(notInCollectionQuery(ids(TIDY_LIST_LIMIT + 1))).toBeNull();
		expect(notInCollectionQuery(ids(TIDY_LIST_LIMIT))).not.toBeNull();
		expect(noTypeQuery([])).toBeNull();
		expect(noTypeQuery(slugs(TIDY_LIST_LIMIT + 1))).toBeNull();
	});
});

describe('tidyRows', () => {
	it('lists all four rows when the id lists fit', () => {
		expect(tidyRows({ collectionIds: ids(2), typeSlugs: slugs(2) }).map((r) => r.id)).toEqual([
			'no-photo',
			'no-description',
			'no-collection',
			'no-type'
		]);
	});

	it('leaves out the rows that cannot be asked accurately', () => {
		expect(tidyRows({ collectionIds: ids(51), typeSlugs: [] }).map((row) => row.id)).toEqual([
			'no-photo',
			'no-description'
		]);
	});
});

describe('itemsHref', () => {
	it('opens the Items page with the same filter', () => {
		const href = itemsHref(noPhotoQuery());
		expect(href.startsWith('/items?')).toBe(true);
		const token = new URLSearchParams(href.split('?')[1]).get(FILTER_PARAM);
		expect(decodeQuery(token!)).toEqual(noPhotoQuery());
	});
});

describe('greeting', () => {
	it.each([
		[5, 'Good morning'],
		[11, 'Good morning'],
		[12, 'Good afternoon'],
		[17, 'Good afternoon'],
		[18, 'Good evening'],
		[23, 'Good evening'],
		[0, 'Good evening'],
		[4, 'Good evening']
	])("at %i o'clock says %s", (hour, text) => {
		expect(greeting(hour)).toBe(text);
	});
});

describe('percent', () => {
	it('rounds to a whole number', () => {
		expect(percent(232, 1284)).toBe(18);
		expect(percent(1, 3)).toBe(33);
	});

	it('is 0 with nothing to divide by and never above 100', () => {
		expect(percent(5, 0)).toBe(0);
		expect(percent(9, 3)).toBe(100);
	});
});
