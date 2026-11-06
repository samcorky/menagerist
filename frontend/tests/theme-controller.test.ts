// The theme controller keeps <meta name="theme-color"> in step with the chosen theme. The suite
// runs in Node, so the few browser globals it touches are stubbed.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { THEME_COLOURS, themeController } from '$lib/theme.svelte';

let content: string | null;
let dark: boolean;
let hasMeta: boolean;

beforeEach(() => {
	content = '#ffffff';
	dark = false;
	hasMeta = true;
	vi.stubGlobal('window', { matchMedia: () => ({ matches: dark }) });
	vi.stubGlobal('localStorage', { setItem: vi.fn() });
	vi.stubGlobal('document', {
		documentElement: { classList: { toggle: vi.fn() } },
		querySelector: (selector: string) =>
			hasMeta && selector === 'meta[name="theme-color"]'
				? { setAttribute: (_: string, value: string) => (content = value) }
				: null
	});
});

afterEach(() => vi.unstubAllGlobals());

describe('theme-color meta tag', () => {
	it('follows the chosen theme', () => {
		themeController.set('dark');
		expect(content).toBe(THEME_COLOURS.dark);
		themeController.set('light');
		expect(content).toBe(THEME_COLOURS.light);
	});

	it('follows the system preference when the theme is system', () => {
		dark = true;
		themeController.set('system');
		expect(content).toBe(THEME_COLOURS.dark);
	});

	it('does nothing when the page has no theme-color tag', () => {
		hasMeta = false;
		expect(() => themeController.set('dark')).not.toThrow();
		expect(content).toBe('#ffffff');
	});
});
