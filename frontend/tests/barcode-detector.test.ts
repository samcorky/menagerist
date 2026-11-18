import { describe, expect, it } from 'vitest';
import { firstCode, nativeFormats } from '$lib/barcode/detector';
import { cameraProblem } from '$lib/barcode/camera';

describe('nativeFormats', () => {
	it('asks a native detector only for the formats it can read', () => {
		expect(nativeFormats(['qr_code', 'aztec', 'ean_13'])).toEqual(['ean_13', 'qr_code']);
	});

	it('is empty when the native detector reads none of them', () => {
		expect(nativeFormats([])).toEqual([]);
	});
});

describe('firstCode', () => {
	it('takes the first non-blank code, trimmed', () => {
		expect(firstCode([{ rawValue: '  ' }, { rawValue: ' 4006381333931\n' }])).toBe('4006381333931');
	});

	it('is null when nothing was read', () => {
		expect(firstCode([])).toBeNull();
	});
});

describe('cameraProblem', () => {
	it.each([
		['NotAllowedError', 'denied'],
		['SecurityError', 'denied'],
		['NotFoundError', 'unavailable'],
		['NotReadableError', 'unavailable'],
		['OverconstrainedError', 'unavailable']
	])('reads %s as %s', (name, problem) => {
		expect(cameraProblem(new DOMException('', name))).toBe(problem);
	});

	it('treats anything else as no camera', () => {
		expect(cameraProblem('odd')).toBe('unavailable');
	});
});
