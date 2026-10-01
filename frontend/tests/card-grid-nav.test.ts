import { describe, it, expect } from 'vitest';
import { nextCardIndex, type CardRect } from '../src/lib/components/card-grid-nav';

describe('nextCardIndex - list mode', () => {
	const rects: CardRect[] = [
		{ top: 0, left: 0 },
		{ top: 60, left: 0 },
		{ top: 120, left: 0 }
	];

	it('moves to the next item on ArrowDown', () => {
		expect(nextCardIndex('ArrowDown', 0, rects, 'list')).toBe(1);
	});

	it('moves to the previous item on ArrowUp', () => {
		expect(nextCardIndex('ArrowUp', 1, rects, 'list')).toBe(0);
	});

	it('returns null moving down from the last item', () => {
		expect(nextCardIndex('ArrowDown', 2, rects, 'list')).toBeNull();
	});

	it('returns null moving up from the first item', () => {
		expect(nextCardIndex('ArrowUp', 0, rects, 'list')).toBeNull();
	});

	it('ignores ArrowLeft/ArrowRight', () => {
		expect(nextCardIndex('ArrowLeft', 1, rects, 'list')).toBeNull();
		expect(nextCardIndex('ArrowRight', 1, rects, 'list')).toBeNull();
	});
});

describe('nextCardIndex - grid mode', () => {
	// 3-column grid, 2 rows, last row has 1 item:
	// [0, 1, 2]
	// [3]
	const rects: CardRect[] = [
		{ top: 0, left: 0 },
		{ top: 0, left: 100 },
		{ top: 0, left: 200 },
		{ top: 150, left: 0 }
	];

	it('moves to the next item in document order on ArrowRight', () => {
		expect(nextCardIndex('ArrowRight', 0, rects, 'grid')).toBe(1);
	});

	it('moves to the previous item in document order on ArrowLeft', () => {
		expect(nextCardIndex('ArrowLeft', 1, rects, 'grid')).toBe(0);
	});

	it('returns null moving left from the first item', () => {
		expect(nextCardIndex('ArrowLeft', 0, rects, 'grid')).toBeNull();
	});

	it('returns null moving right from the last item', () => {
		expect(nextCardIndex('ArrowRight', 3, rects, 'grid')).toBeNull();
	});

	it('moves down to the card in the next row with the closest left offset', () => {
		expect(nextCardIndex('ArrowDown', 1, rects, 'grid')).toBe(3);
	});

	it('moves up to the card in the previous row with the closest left offset', () => {
		expect(nextCardIndex('ArrowUp', 3, rects, 'grid')).toBe(0);
	});

	it('returns null moving down from the last row', () => {
		expect(nextCardIndex('ArrowDown', 3, rects, 'grid')).toBeNull();
	});

	it('returns null moving up from the first row', () => {
		expect(nextCardIndex('ArrowUp', 0, rects, 'grid')).toBeNull();
	});

	it('picks the nearest column by left offset, not just the first in the row', () => {
		const wideRects: CardRect[] = [
			{ top: 0, left: 0 },
			{ top: 0, left: 100 },
			{ top: 0, left: 200 },
			{ top: 150, left: 0 },
			{ top: 150, left: 100 },
			{ top: 150, left: 200 }
		];
		// From index 1 (left: 100, top: 0), ArrowDown should land on index 4 (left: 100, top: 150).
		expect(nextCardIndex('ArrowDown', 1, wideRects, 'grid')).toBe(4);
	});
});

describe('nextCardIndex - out of range', () => {
	it('returns null for an out-of-range current index', () => {
		expect(nextCardIndex('ArrowDown', 5, [{ top: 0, left: 0 }], 'grid')).toBeNull();
	});
});
