import { describe, it, expect } from 'vitest';

process.env.TZ = 'America/Los_Angeles';

import { formatIsoDate, formatRelativeTime } from '../src/lib/format-date';

describe('formatIsoDate', () => {
	it('does not shift the day in a negative UTC offset', () => {
		expect(formatIsoDate('2024-03-15', 'long')).toContain('15');
		expect(formatIsoDate('2024-03-15', 'short')).toContain('15');
	});

	it('returns the input when it is not a date', () => {
		expect(formatIsoDate('not a date', 'long')).toBe('not a date');
	});
});

describe('formatRelativeTime', () => {
	const now = new Date('2024-03-15T12:00:00Z');

	it('says "just now" within 30 seconds either way', () => {
		expect(formatRelativeTime('2024-03-15T11:59:35Z', now)).toBe('just now');
		expect(formatRelativeTime('2024-03-15T12:00:25Z', now)).toBe('just now');
	});

	it("formats a past timestamp with date-fns' conversational wording", () => {
		expect(formatRelativeTime('2024-03-15T10:00:00Z', now)).toBe('about 2 hours ago');
		expect(formatRelativeTime('2024-03-14T12:00:00Z', now)).toBe('1 day ago');
	});

	it('clamps any future timestamp to "just now" (clock drift/a stale `now`, never real)', () => {
		expect(formatRelativeTime('2024-03-15T12:00:05Z', now)).toBe('just now');
		expect(formatRelativeTime('2024-03-15T14:00:00Z', now)).toBe('just now');
	});

	it('returns the input when it is not a date', () => {
		expect(formatRelativeTime('not a date', now)).toBe('not a date');
	});
});
