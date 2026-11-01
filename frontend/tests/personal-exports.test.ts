import { describe, expect, it } from 'vitest';
import { describeExportExpiry, formatExportSize } from '../src/lib/personal-exports';

const now = new Date('2026-10-24T12:00:00Z');

describe('formatExportSize', () => {
	it('uses KB below a megabyte', () => {
		expect(formatExportSize(2048)).toBe('2.0 KB');
	});
	it('uses MB from a megabyte up', () => {
		expect(formatExportSize(1048576)).toBe('1.0 MB');
		expect(formatExportSize(5 * 1048576 + 524288)).toBe('5.5 MB');
	});
});

describe('describeExportExpiry', () => {
	it('words the time left', () => {
		expect(describeExportExpiry('2026-10-25T11:00:00Z', now)).toBe('Expires in about 23 hours');
		expect(describeExportExpiry('2026-10-24T12:05:00Z', now)).toBe('Expires in 5 minutes');
	});
	it('handles the last minute and the past', () => {
		expect(describeExportExpiry('2026-10-24T12:00:30Z', now)).toBe('Expires in under a minute');
		expect(describeExportExpiry('2026-10-24T11:59:00Z', now)).toBe('Expired');
	});
	it('copes with an unreadable date', () => {
		expect(describeExportExpiry('nope', now)).toBe('Expires soon');
	});
});
