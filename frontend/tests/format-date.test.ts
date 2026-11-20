import { describe, it, expect } from 'vitest';

process.env.TZ = 'America/Los_Angeles';

import {
	browserKnowsZone,
	formatDateTime,
	formatIsoDate,
	formatPartialDate,
	formatRelativeTime,
	formatTime,
	knownZones,
	resolvedZone,
	zoneOffset,
	type DateTimePrefs
} from '../src/lib/format-date';

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

describe('date and time preferences', () => {
	const at = '2026-12-31T22:30:00Z';
	const base: DateTimePrefs = {
		zone: 'browser',
		order: 'automatic',
		clock: 'automatic',
		locale: 'en-GB'
	};

	it('writes calendar dates in the chosen order, never shifted by the zone', () => {
		const tokyo = { ...base, zone: 'Asia/Tokyo' };
		expect(formatIsoDate('2026-03-05', 'short', { ...tokyo, order: 'dmy' })).toBe('5 Mar 2026');
		expect(formatIsoDate('2026-03-05', 'short', { ...tokyo, order: 'mdy' })).toBe('Mar 5, 2026');
		expect(formatIsoDate('2026-03-05', 'long', { ...tokyo, order: 'ymd' })).toBe('2026-03-05');
		expect(formatIsoDate('2026-03-05', 'long', { ...tokyo, order: 'dmy' })).toBe('5 March 2026');
	});

	it('keeps partial dates at their precision in each order', () => {
		expect(formatPartialDate('1973-03', 'short', { ...base, order: 'ymd' })).toBe('1973-03');
		expect(formatPartialDate('1973-03', 'short', { ...base, order: 'dmy' })).toBe('Mar 1973');
		expect(formatPartialDate('1973', 'short', { ...base, order: 'mdy' })).toBe('1973');
	});

	it('shows timestamps in the chosen zone, naming it when it is not the device one', () => {
		const tokyo = formatDateTime(
			at,
			{},
			{ ...base, zone: 'Asia/Tokyo', order: 'dmy', clock: '24h' }
		);
		expect(tokyo.local).toBe('1 Jan 2027, 07:30 GMT+9');
		expect(tokyo.utc).toBe('31 Dec 2026, 22:30 UTC');

		const here = formatDateTime(at, {}, { ...base, order: 'dmy', clock: '24h' });
		expect(here.local).toBe('31 Dec 2026, 14:30');
		const named = formatDateTime(
			at,
			{},
			{ ...base, zone: 'America/Los_Angeles', order: 'dmy', clock: '24h' }
		);
		expect(named.local).toBe('31 Dec 2026, 14:30');
	});

	it('follows the chosen clock', () => {
		const prefs = { ...base, zone: 'UTC', order: 'dmy' as const };
		expect(formatTime(at, { ...prefs, clock: '24h' })).toMatch(/^22:30/);
		expect(formatTime(at, { ...prefs, clock: '12h' })).toMatch(/^10:30\s?pm/i);
		expect(formatDateTime(at, { seconds: true }, { ...prefs, clock: '24h' }).local).toContain(
			'22:30:00'
		);
	});

	it('falls back to the device zone for one the browser does not know', () => {
		const unknown = {
			...base,
			zone: 'Mars/Olympus_Mons',
			order: 'dmy' as const,
			clock: '24h' as const
		};
		expect(browserKnowsZone('Mars/Olympus_Mons')).toBe(false);
		expect(browserKnowsZone('Asia/Tokyo')).toBe(true);
		expect(resolvedZone(unknown)).toBe('America/Los_Angeles');
		// Formats in the device zone, with no marker, rather than throwing.
		expect(formatDateTime(at, {}, unknown).local).toBe('31 Dec 2026, 14:30');
		expect(formatTime(at, unknown)).toBe('14:30');
	});

	it('resolves the browser zone and names offsets', () => {
		expect(resolvedZone(base)).toBe('America/Los_Angeles');
		expect(resolvedZone({ ...base, zone: 'Asia/Tokyo' })).toBe('Asia/Tokyo');
		expect(zoneOffset('Asia/Tokyo')).toBe('GMT+9');
		expect(zoneOffset('Not/AZone')).toBe('');
		expect(knownZones()).toContain('Europe/London');
	});
});
