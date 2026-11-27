import { describe, expect, it } from 'vitest';
import {
	countedEnd,
	endMessage,
	listEndState,
	loadAheadMargin,
	pageRangeMessage,
	LOAD_MORE_FAILED
} from '$lib/list-end';

const paging = (over: Partial<Parameters<typeof listEndState>[0]> = {}) =>
	listEndState({ loading: false, hasMore: false, failed: false, rows: 5, ...over });

describe('listEndState', () => {
	it('reports the end once the last page has loaded', () => {
		expect(paging()).toBe('end');
	});

	it('reports loading only once there are rows, so the skeleton stands alone', () => {
		expect(paging({ loading: true, hasMore: true })).toBe('loading');
		expect(paging({ loading: true, hasMore: true, rows: 0 })).toBe('idle');
	});

	it('says nothing while more pages are still to come', () => {
		expect(paging({ hasMore: true })).toBe('idle');
	});

	it('leaves an empty list to its own empty state', () => {
		expect(paging({ rows: 0 })).toBe('idle');
	});

	it('puts a failed page ahead of every other state', () => {
		expect(paging({ failed: true, loading: true, hasMore: true })).toBe('failed');
		expect(paging({ failed: true, rows: 0 })).toBe('failed');
	});
});

describe('loadAheadMargin', () => {
	it('loads two and a half screens ahead', () => {
		expect(loadAheadMargin(800)).toBe('2000px');
	});

	it('is always further ahead than the old 200px', () => {
		for (const height of [320, 568, 800, 1440, 2160]) {
			expect(Number.parseInt(loadAheadMargin(height), 10)).toBeGreaterThan(200);
		}
	});

	it('falls back to a sensible margin for a height it cannot read', () => {
		expect(loadAheadMargin(0)).toBe('2000px');
		expect(loadAheadMargin(Number.NaN)).toBe('2000px');
	});
});

describe('countedEnd', () => {
	it('groups thousands and pluralises the noun', () => {
		expect(countedEnd(50, 1204, 'item')).toBe('1,204 items');
		expect(countedEnd(1, 1, 'item')).toBe('1 item');
		expect(countedEnd(3, 3, 'item type')).toBe('3 item types');
	});

	it('counts the loaded rows where the server gave no total', () => {
		expect(countedEnd(7, null, 'collection')).toBe('7 collections');
	});
});

describe('endMessage', () => {
	const lines = ['All done.', 'Nothing further.'];

	it('stays plain and factual for a short list', () => {
		expect(endMessage(5, 5, 'item', lines, '/items')).toBe("That's everything - 5 items.");
	});

	it('adds a flavour line with the count once the list is long', () => {
		const message = endMessage(40, 1204, 'item', lines, '/items');
		expect(lines.some((line) => message.startsWith(line))).toBe(true);
		expect(message).toContain('1,204 items in all.');
	});

	it('is stable for the same list within a session', () => {
		expect(endMessage(40, 40, 'item', lines, '/items')).toBe(
			endMessage(40, 40, 'item', lines, '/items')
		);
	});

	it('manages without any flavour lines', () => {
		expect(endMessage(40, 40, 'item', [], '/items')).toBe("That's everything - 40 items.");
	});
});

describe('LOAD_MORE_FAILED', () => {
	it('is plain, with no flavour and no jargon', () => {
		expect(LOAD_MORE_FAILED).toBe("We couldn't load any more.");
	});
});

describe('pageRangeMessage', () => {
	it("places the page in the whole list, with the server's count", () => {
		expect(pageRangeMessage(26, 50, 312, 'session', false)).toBe('26–50 of 312 sessions');
		expect(pageRangeMessage(1, 25, 1204, 'user', false)).toBe('1–25 of 1,204 users');
	});

	it('places it without a count when the server sent none', () => {
		expect(pageRangeMessage(26, 50, null, 'session', false)).toBe('26–50 sessions');
	});

	it('says how many there are when the list fits one page', () => {
		expect(pageRangeMessage(1, 5, 5, 'token', true)).toBe('5 tokens');
		expect(pageRangeMessage(1, 1, 1, 'token', true)).toBe('1 token');
		expect(pageRangeMessage(1, 3, null, 'token', true)).toBe('3 tokens');
	});
});
