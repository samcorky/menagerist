import { describe, expect, it } from 'vitest';
import {
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
	formatPercent,
	percent,
	photoQuery,
	tidyRows
} from '$lib/dashboard';
import { decodeQuery, parseQuery } from '$lib/query/codec';
import { FILTER_PARAM } from '$lib/query/items-page';

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
			notInCollectionQuery(),
			noTypeQuery()
		]) {
			expect(parseQuery(JSON.parse(JSON.stringify(query)))).not.toBeNull();
		}
	});
});

describe('queries that need no list', () => {
	it('finds items in no collection, however many collections there are', () => {
		expect(notInCollectionQuery().where?.children).toEqual([{ kind: 'collection', mode: 'none' }]);
	});

	it('finds items with no item type at all', () => {
		expect(noTypeQuery().where?.children).toEqual([{ kind: 'type', mode: 'none' }]);
	});
});

describe('tidyRows', () => {
	it('always lists all four rows, with no collection or type lists to build', () => {
		expect(tidyRows().map((r) => r.id)).toEqual([
			'no-photo',
			'no-description',
			'no-collection',
			'no-type'
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
		[23, 'Good evening']
	])("at %i o'clock says %s", (hour, text) => {
		expect(greeting(hour, 's1')).toBe(text);
	});

	it.each([0, 1, 4])("at %i o'clock uses a small-hours line, steady for a session", (hour) => {
		const line = greeting(hour, 's1');
		expect(line).not.toMatch(/^Good /);
		expect(greeting(hour, 's1')).toBe(line);
	});

	it('varies the small-hours line between sessions', () => {
		const seen = new Set(Array.from({ length: 50 }, (_, i) => greeting(2, `seed-${i}`)));
		expect(seen.size).toBeGreaterThan(1);
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

describe('formatPercent', () => {
	it('reads <1% when something is there but rounds to nothing', () => {
		expect(formatPercent(1, 400)).toBe('<1%');
	});

	it('reads >99% when something is missing but it rounds to everything', () => {
		expect(formatPercent(399, 400)).toBe('>99%');
	});

	it('keeps 100% for all of them, or more than all', () => {
		expect(formatPercent(400, 400)).toBe('100%');
		expect(formatPercent(9, 3)).toBe('100%');
	});

	it('keeps 0% for a count of zero or nothing to divide by', () => {
		expect(formatPercent(0, 400)).toBe('0%');
		expect(formatPercent(0, 0)).toBe('0%');
		expect(formatPercent(3, 0)).toBe('0%');
	});

	it('is the plain rounded share otherwise', () => {
		expect(formatPercent(232, 1284)).toBe('18%');
		expect(formatPercent(9, 3)).toBe('100%');
	});
});
