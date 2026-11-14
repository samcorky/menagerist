import { describe, expect, it } from 'vitest';
import { shouldCloseSheet } from '$lib/sheet-drag';

describe('shouldCloseSheet', () => {
	it('closes once pulled past a third of the height', () => {
		expect(shouldCloseSheet(300, 800, 0.05)).toBe(true);
	});

	it('springs back when let go early and slowly', () => {
		expect(shouldCloseSheet(100, 800, 0.1)).toBe(false);
	});

	it('closes on a quick flick however short', () => {
		expect(shouldCloseSheet(40, 800, 0.9)).toBe(true);
	});

	it('never closes on an upward or zero drag', () => {
		expect(shouldCloseSheet(-50, 800, 2)).toBe(false);
		expect(shouldCloseSheet(0, 800, 2)).toBe(false);
	});
});
