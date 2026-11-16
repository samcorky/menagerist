import { afterEach, describe, expect, it, vi } from 'vitest';
import { hashString, pickEmptyLine, sessionSeed } from '$lib/empty-lines';

const lines = ['a', 'b', 'c', 'd', 'e'];

afterEach(() => vi.unstubAllGlobals());

describe('pickEmptyLine', () => {
	it('gives the same line for the same seed and key', () => {
		expect(pickEmptyLine(lines, '/items', 's1')).toBe(pickEmptyLine(lines, '/items', 's1'));
	});

	it('reaches every line as the seed varies', () => {
		const seen = new Set(
			Array.from({ length: 200 }, (_, i) => pickEmptyLine(lines, '/items', `seed-${i}`))
		);
		expect(seen).toEqual(new Set(lines));
	});

	it('reaches every line as the page varies', () => {
		const seen = new Set(
			Array.from({ length: 200 }, (_, i) => pickEmptyLine(lines, `/collections/${i}`, 's1'))
		);
		expect(seen).toEqual(new Set(lines));
	});

	it('returns the only line of a single-line set', () => {
		expect(pickEmptyLine(['only'], '/items', 's1')).toBe('only');
	});

	it('refuses an empty set', () => {
		expect(() => pickEmptyLine([], '/items', 's1')).toThrow();
	});
});

describe('hashString', () => {
	it('is stable and unsigned', () => {
		expect(hashString('menagerist')).toBe(hashString('menagerist'));
		expect(hashString('')).toBe(0x811c9dc5);
		expect(hashString('a|b')).toBeGreaterThanOrEqual(0);
	});
});

describe('sessionSeed', () => {
	it('is created once and then reused from session storage', () => {
		const store = new Map<string, string>();
		vi.stubGlobal('sessionStorage', {
			getItem: (k: string) => store.get(k) ?? null,
			setItem: (k: string, v: string) => void store.set(k, v)
		});
		const first = sessionSeed();
		expect(first).not.toBe('');
		expect(sessionSeed()).toBe(first);
		expect([...store.values()]).toEqual([first]);
	});

	it('still returns a steady value when storage is unavailable', () => {
		vi.stubGlobal('sessionStorage', {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			}
		});
		const seed = sessionSeed();
		expect(seed).not.toBe('');
		expect(sessionSeed()).toBe(seed);
	});
});
