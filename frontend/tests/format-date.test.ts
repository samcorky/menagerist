import { describe, it, expect } from 'vitest';

process.env.TZ = 'America/Los_Angeles';

import { formatIsoDate } from '../src/lib/format-date';

describe('formatIsoDate', () => {
	it('does not shift the day in a negative UTC offset', () => {
		expect(formatIsoDate('2024-03-15', 'long')).toContain('15');
		expect(formatIsoDate('2024-03-15', 'short')).toContain('15');
	});

	it('returns the input when it is not a date', () => {
		expect(formatIsoDate('not a date', 'long')).toBe('not a date');
	});
});
