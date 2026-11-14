import { describe, expect, it } from 'vitest';
import { displayMode, readStandalone } from '../src/lib/display-mode.svelte';

function fakeWindow(initial: boolean) {
	let matches = initial;
	const listeners = new Set<() => void>();
	const query = {
		get matches() {
			return matches;
		},
		addEventListener: (_: string, listener: () => void) => listeners.add(listener),
		removeEventListener: (_: string, listener: () => void) => listeners.delete(listener)
	};
	return {
		env: { matchMedia: () => query, navigator: {} } as unknown as Window,
		set(value: boolean) {
			matches = value;
			for (const listener of listeners) listener();
		},
		listeners
	};
}

describe('readStandalone', () => {
	it('is true when the display-mode query matches', () => {
		expect(readStandalone({ matchMedia: () => ({ matches: true }) })).toBe(true);
	});

	it('falls back to navigator.standalone on older iOS', () => {
		expect(
			readStandalone({ matchMedia: () => ({ matches: false }), navigator: { standalone: true } })
		).toBe(true);
		expect(readStandalone({ navigator: { standalone: true } })).toBe(true);
	});

	it('is false in a browser tab', () => {
		expect(readStandalone({ matchMedia: () => ({ matches: false }), navigator: {} })).toBe(false);
		expect(readStandalone({})).toBe(false);
	});
});

describe('displayMode', () => {
	it('follows changes until cleaned up', () => {
		const fake = fakeWindow(true);
		const stop = displayMode.init(fake.env);
		expect(displayMode.standalone).toBe(true);
		expect(displayMode.mode).toBe('standalone');

		fake.set(false);
		expect(displayMode.mode).toBe('browser');

		stop();
		expect(fake.listeners.size).toBe(0);
		fake.set(true);
		expect(displayMode.mode).toBe('browser');
	});

	it('does nothing without matchMedia', () => {
		const stop = displayMode.init({} as Window);
		expect(typeof stop).toBe('function');
		stop();
	});
});
