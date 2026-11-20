import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFlag, readList, readOptionalFlag, writeFlag, writeList } from '$lib/remembered';

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

describe('remembered lists', () => {
	it('round-trips a list in order and reads [] when nothing is stored', () => {
		vi.stubGlobal('localStorage', memoryStorage());
		expect(readList('l')).toEqual([]);
		writeList('l', ['b', 'a']);
		expect(readList('l')).toEqual(['b', 'a']);
	});

	it('reads [] from unreadable JSON and drops anything that is not a string', () => {
		const storage = memoryStorage();
		vi.stubGlobal('localStorage', storage);
		storage.setItem('menagerist:l', '{oops');
		expect(readList('l')).toEqual([]);
		storage.setItem('menagerist:l', '["a", 1, null, "b"]');
		expect(readList('l')).toEqual(['a', 'b']);
		storage.setItem('menagerist:l', '{"a": 1}');
		expect(readList('l')).toEqual([]);
	});

	it('falls back when storage throws', () => {
		vi.stubGlobal('localStorage', {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			}
		});
		expect(readList('l')).toEqual([]);
		expect(() => writeList('l', ['a'])).not.toThrow();
	});
});
