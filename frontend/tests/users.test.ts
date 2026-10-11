import { describe, expect, it } from 'vitest';
import { isLocked, lastSignIn, lockedLabel } from '../src/lib/users';

const now = new Date('2026-10-11T12:00:00Z');

describe('isLocked', () => {
	it('is true only while the lockout is in the future', () => {
		expect(isLocked('2026-10-11T12:10:00Z', now)).toBe(true);
		expect(isLocked('2026-10-11T11:59:00Z', now)).toBe(false);
		expect(isLocked(null, now)).toBe(false);
		expect(isLocked(undefined, now)).toBe(false);
		expect(isLocked('nonsense', now)).toBe(false);
	});
});

describe('lockedLabel', () => {
	it('names the time the lock ends', () => {
		expect(lockedLabel('2026-10-11T12:10:00Z')).toMatch(/^Locked until \d/);
		expect(lockedLabel('nonsense')).toBe('Locked');
	});
});

describe('lastSignIn', () => {
	it('says Never when there is no sign-in', () => {
		expect(lastSignIn(null, now)).toEqual({ text: 'Never' });
		expect(lastSignIn(undefined, now)).toEqual({ text: 'Never' });
		expect(lastSignIn('nonsense', now)).toEqual({ text: 'Never' });
	});

	it('gives a relative time with the full date as a title', () => {
		const result = lastSignIn('2026-10-11T09:00:00Z', now);
		expect(result.text).toBe('about 3 hours ago');
		expect(result.title).toBeTruthy();
		expect(lastSignIn('2026-10-11T11:59:50Z', now).text).toBe('just now');
	});
});
