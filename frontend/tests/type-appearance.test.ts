import { describe, expect, it } from 'vitest';
import contract from '$shared/contracts/type-colours.json';
import { TYPE_ICONS } from '$lib/type-icons';
import {
	TYPE_COLOUR_KEYS,
	colourClasses,
	isKnownIcon,
	randomColour,
	randomIcon,
	searchIcons
} from '$lib/type-appearance';

describe('colour palette', () => {
	it('is the shared contract, in order', () => {
		expect([...TYPE_COLOUR_KEYS]).toEqual(contract.colours);
	});

	it('has text and background classes, with dark-mode text, for every colour', () => {
		for (const key of TYPE_COLOUR_KEYS) {
			const classes = colourClasses(key);
			expect(classes.text).toMatch(/dark:text-/);
			expect(classes.background).toMatch(/^bg-/);
			expect(classes.swatch).toMatch(/^bg-[a-z]+-500$/);
		}
	});

	it('uses the neutral colour for none or an unknown name', () => {
		expect(colourClasses(null)).toEqual(colourClasses('gray'));
		expect(colourClasses('purple')).toEqual(colourClasses('gray'));
	});
});

describe('icons', () => {
	it('knows the icons it can draw and nothing else', () => {
		expect(isKnownIcon('film')).toBe(true);
		expect(isKnownIcon('disc-3')).toBe(true);
		expect(isKnownIcon('not-an-icon')).toBe(false);
		expect(isKnownIcon(null)).toBe(false);
	});

	it('offers a good spread of icons', () => {
		expect(Object.keys(TYPE_ICONS).length).toBeGreaterThanOrEqual(100);
	});

	it('lists every icon for a blank search', () => {
		expect(searchIcons('')).toEqual(Object.keys(TYPE_ICONS));
		expect(searchIcons('   ')).toHaveLength(Object.keys(TYPE_ICONS).length);
	});

	it('finds an icon by its name or by words people use for it', () => {
		expect(searchIcons('clap')).toContain('clapperboard');
		expect(searchIcons('vinyl')).toContain('disc-3');
		expect(searchIcons('MOVIE')).toEqual(expect.arrayContaining(['film', 'clapperboard']));
	});

	it('needs every typed word to match', () => {
		expect(searchIcons('movie cinema')).toContain('film');
		expect(searchIcons('movie zzzz')).toEqual([]);
	});

	it('puts name matches before matches in the search words', () => {
		const results = searchIcons('film');
		expect(results[0]).toBe('film');
	});
});

describe('randomising', () => {
	it('picks an icon and a colour from the available ones', () => {
		for (const roll of [0, 0.25, 0.5, 0.999999]) {
			expect(isKnownIcon(randomIcon(() => roll))).toBe(true);
			expect(TYPE_COLOUR_KEYS).toContain(randomColour(() => roll));
		}
	});

	it('maps the random number across the whole list', () => {
		const names = Object.keys(TYPE_ICONS);
		expect(randomIcon(() => 0)).toBe(names[0]);
		expect(randomIcon(() => 0.999999)).toBe(names[names.length - 1]);
	});

	it('can avoid repeating the current choice', () => {
		const names = Object.keys(TYPE_ICONS);
		expect(randomIcon(() => 0, names[0])).not.toBe(names[0]);
		expect(randomColour(() => 0, TYPE_COLOUR_KEYS[0])).not.toBe(TYPE_COLOUR_KEYS[0]);
	});
});
