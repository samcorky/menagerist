import { describe, expect, it, vi } from 'vitest';
import { firstCode, nativeFormats } from '$lib/barcode/detector';
import { cameraProblem, hasTorch, setTorch } from '$lib/barcode/camera';

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

/** A stream whose one video track reports these capabilities. */
function streamWith(capabilities: object | undefined, applyConstraints = vi.fn()) {
	const track = { applyConstraints, getCapabilities: capabilities && (() => capabilities) };
	return { getVideoTracks: () => [track] } as unknown as MediaStream;
}

describe('hasTorch', () => {
	it('is true when the camera reports a torch', () => {
		expect(hasTorch(streamWith({ torch: true }))).toBe(true);
	});

	it('is false when it does not, or the browser cannot say', () => {
		expect(hasTorch(streamWith({}))).toBe(false);
		expect(hasTorch(streamWith(undefined))).toBe(false);
		expect(hasTorch(null)).toBe(false);
	});
});

describe('setTorch', () => {
	it('switches the light with an advanced constraint', async () => {
		const applyConstraints = vi.fn().mockResolvedValue(undefined);

		expect(await setTorch(streamWith({ torch: true }, applyConstraints), true)).toBe(true);
		expect(applyConstraints).toHaveBeenCalledWith({ advanced: [{ torch: true }] });
	});

	it('says so when the browser refuses', async () => {
		const refuse = vi.fn().mockRejectedValue(new DOMException('', 'OverconstrainedError'));

		expect(await setTorch(streamWith({ torch: true }, refuse), true)).toBe(false);
		expect(await setTorch(null, true)).toBe(false);
	});
});
