import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFlag, readOptionalFlag, writeFlag } from '$lib/remembered';

function memoryStorage() {
	const data = new Map<string, string>();
	return {
		data,
		getItem: (key: string) => data.get(key) ?? null,
		setItem: (key: string, value: string) => void data.set(key, value)
	};
}

afterEach(() => vi.unstubAllGlobals());

describe('remembered flags', () => {
	it('reads the fallback when nothing is stored', () => {
		vi.stubGlobal('localStorage', memoryStorage());
		expect(readFlag('a', true)).toBe(true);
		expect(readFlag('a', false)).toBe(false);
	});

	it('round-trips a flag', () => {
		vi.stubGlobal('localStorage', memoryStorage());
		writeFlag('a', false);
		expect(readFlag('a', true)).toBe(false);
		writeFlag('a', true);
		expect(readFlag('a', false)).toBe(true);
	});

	it('namespaces its keys', () => {
		const storage = memoryStorage();
		vi.stubGlobal('localStorage', storage);
		writeFlag('section:x', true);
		expect([...storage.data.keys()]).toEqual(['menagerist:section:x']);
	});

	it('falls back when storage throws', () => {
		const broken = {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			}
		};
		vi.stubGlobal('localStorage', broken);
		expect(readFlag('a', true)).toBe(true);
		expect(() => writeFlag('a', false)).not.toThrow();
	});

	it('falls back when there is no storage at all', () => {
		vi.stubGlobal('localStorage', undefined);
		expect(readFlag('a', false)).toBe(false);
		expect(() => writeFlag('a', true)).not.toThrow();
	});
});

describe('optional flags', () => {
	it('is undefined until something is stored', () => {
		vi.stubGlobal('localStorage', memoryStorage());
		expect(readOptionalFlag('a')).toBeUndefined();
		writeFlag('a', false);
		expect(readOptionalFlag('a')).toBe(false);
	});

	it('is undefined when storage throws', () => {
		vi.stubGlobal('localStorage', {
			getItem: () => {
				throw new Error('blocked');
			}
		});
		expect(readOptionalFlag('a')).toBeUndefined();
	});
});
