import { describe, expect, it } from 'vitest';
import { itemCount, leavesPage, parseTagInput, unknownItemIds } from '../src/lib/bulk-actions';

describe('unknownItemIds', () => {
	it('reads the ids out of the server message', () => {
		const a = '01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10';
		const b = '01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e11';
		expect(unknownItemIds(`Unknown or deleted items: ${a}, ${b}`)).toEqual([a, b]);
	});

	it('is empty for any other message', () => {
		expect(unknownItemIds('Choose at least one item')).toEqual([]);
		expect(unknownItemIds(undefined)).toEqual([]);
	});
});

describe('itemCount', () => {
	it('pluralises', () => {
		expect(itemCount(1)).toBe('1 item');
		expect(itemCount(3)).toBe('3 items');
	});
});

describe('parseTagInput', () => {
	it('splits on commas and drops blanks and repeats', () => {
		expect(parseTagInput(' sci-fi, horror,, sci-fi ,')).toEqual(['sci-fi', 'horror']);
		expect(parseTagInput('')).toEqual([]);
	});
});

describe('leavesPage', () => {
	const at = (path: string) => ({ url: new URL(`http://x${path}`) });

	it('is false for a search or filter change on the same page', () => {
		expect(leavesPage({ from: at('/items'), to: at('/items?q=a'), willUnload: false })).toBe(false);
	});

	it('is true for another page, another collection, or closing the tab', () => {
		expect(leavesPage({ from: at('/items'), to: at('/home'), willUnload: false })).toBe(true);
		expect(
			leavesPage({ from: at('/collections/a'), to: at('/collections/b'), willUnload: false })
		).toBe(true);
		expect(leavesPage({ from: at('/items'), to: null, willUnload: true })).toBe(true);
	});
});
