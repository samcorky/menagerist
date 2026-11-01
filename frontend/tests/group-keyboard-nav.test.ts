import { describe, it, expect } from 'vitest';
import { shouldMoveCell, nextCellPosition } from '../src/lib/field-types/group/keyboard-nav';

describe('shouldMoveCell', () => {
	it('always moves cells on ArrowUp', () => {
		expect(shouldMoveCell('ArrowUp', { atStart: false, atEnd: false })).toBe(true);
	});

	it('always moves cells on ArrowDown', () => {
		expect(shouldMoveCell('ArrowDown', { atStart: false, atEnd: false })).toBe(true);
	});

	it('moves cells on ArrowLeft only when the caret is at the start', () => {
		expect(shouldMoveCell('ArrowLeft', { atStart: true, atEnd: false })).toBe(true);
		expect(shouldMoveCell('ArrowLeft', { atStart: false, atEnd: false })).toBe(false);
	});

	it('moves cells on ArrowRight only when the caret is at the end', () => {
		expect(shouldMoveCell('ArrowRight', { atStart: false, atEnd: true })).toBe(true);
		expect(shouldMoveCell('ArrowRight', { atStart: false, atEnd: false })).toBe(false);
	});
});

describe('nextCellPosition', () => {
	it('moves down within bounds', () => {
		expect(nextCellPosition({ row: 0, col: 0 }, 'ArrowDown', 3, 2)).toEqual({ row: 1, col: 0 });
	});

	it('moves right within bounds', () => {
		expect(nextCellPosition({ row: 0, col: 0 }, 'ArrowRight', 3, 2)).toEqual({ row: 0, col: 1 });
	});

	it('returns null when moving up from the first row', () => {
		expect(nextCellPosition({ row: 0, col: 0 }, 'ArrowUp', 3, 2)).toBeNull();
	});

	it('returns null when moving down from the last row', () => {
		expect(nextCellPosition({ row: 2, col: 0 }, 'ArrowDown', 3, 2)).toBeNull();
	});

	it('returns null when moving left from the first column', () => {
		expect(nextCellPosition({ row: 0, col: 0 }, 'ArrowLeft', 3, 2)).toBeNull();
	});

	it('returns null when moving right from the last column', () => {
		expect(nextCellPosition({ row: 0, col: 1 }, 'ArrowRight', 3, 2)).toBeNull();
	});
});
