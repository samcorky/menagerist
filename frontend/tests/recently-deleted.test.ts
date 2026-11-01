import { describe, expect, it } from 'vitest';
import {
	deletedCollectionBadge,
	deletedItemType,
	describeDeleted,
	filterByName,
	nextCursor,
	purgeDescription,
	deletedActionError
} from '../src/lib/recently-deleted';

const now = new Date('2026-10-25T12:00:00Z');

describe('describeDeleted', () => {
	it('words elapsed time', () => {
		expect(describeDeleted('2026-10-25T11:59:40Z', now)).toBe('Deleted just now');
		expect(describeDeleted('2026-10-25T11:59:00Z', now)).toBe('Deleted 1 minute ago');
		expect(describeDeleted('2026-10-25T11:15:00Z', now)).toBe('Deleted 45 minutes ago');
		expect(describeDeleted('2026-10-25T09:00:00Z', now)).toBe('Deleted 3 hours ago');
		expect(describeDeleted('2026-10-22T12:00:00Z', now)).toBe('Deleted 3 days ago');
		expect(describeDeleted('2026-07-25T12:00:00Z', now)).toBe('Deleted 3 months ago');
		expect(describeDeleted('2022-10-25T12:00:00Z', now)).toBe('Deleted 4 years ago');
	});
	it('treats a future or invalid time sensibly', () => {
		expect(describeDeleted('2026-10-25T12:30:00Z', now)).toBe('Deleted just now');
		expect(describeDeleted('nope', now)).toBe('Deleted');
	});
});

describe('labels', () => {
	it('prefers the type label, then the slug', () => {
		expect(deletedItemType('film', { film: 'Film' })).toBe('Film');
		expect(deletedItemType('gone', {})).toBe('gone');
		expect(deletedItemType(null, {})).toBeNull();
	});
	it('badges collections', () => {
		expect(deletedCollectionBadge('dynamic')).toBe('Smart');
		expect(deletedCollectionBadge('manual')).toBe('List');
	});
	it('words the purge warning', () => {
		expect(purgeDescription('Alien')).toBe(
			'This permanently deletes Alien. This cannot be undone.'
		);
	});
});

describe('nextCursor', () => {
	const rows = [{ id: 'a' }, { id: 'b' }];
	it('returns the last id when a next link exists', () => {
		expect(nextCursor('</x?after=b>; rel="next"', rows)).toBe('b');
	});
	it('returns null without a next link or rows', () => {
		expect(nextCursor(null, rows)).toBeNull();
		expect(nextCursor('</x>; rel="prev"', rows)).toBeNull();
		expect(nextCursor('</x>; rel="next"', [])).toBeNull();
	});
});

describe('deletedActionError', () => {
	it('keeps the server wording for a conflict', () => {
		expect(deletedActionError('restore', 409, 'Item type film was deleted.')).toBe(
			'Item type film was deleted.'
		);
	});
	it('words other failures plainly', () => {
		expect(deletedActionError('purge', 404, '')).toMatch(/already been removed/);
		expect(deletedActionError('purge', 403, '')).toBe('You do not have permission to purge this.');
		expect(deletedActionError('restore', undefined, '')).toMatch(/offline/);
		expect(deletedActionError('restore', 500, '')).toBe('Could not restore this. Try again.');
	});
});

describe('filterByName', () => {
	const rows = [{ name: 'Alien' }, { name: 'Aliens' }, { name: 'Heat' }];
	it('filters ignoring case', () => {
		expect(filterByName(rows, ' ALIEN ')).toHaveLength(2);
		expect(filterByName(rows, '')).toHaveLength(3);
	});
});
