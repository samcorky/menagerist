export type ArrowKey = 'ArrowUp' | 'ArrowDown' | 'ArrowLeft' | 'ArrowRight';

export type CaretInfo = { atStart: boolean; atEnd: boolean };

/**
 * Whether an arrow key press inside a text-like table cell input should move
 * focus to the adjacent cell (true) or be left to move the text cursor
 * (false). Only call this for plain text/number-ish `<input>` elements -
 * selects, buttons, switches and the rating widget keep their own
 * arrow-key behaviour and must never be routed through this check.
 */
export function shouldMoveCell(key: ArrowKey, caret: CaretInfo): boolean {
	if (key === 'ArrowUp' || key === 'ArrowDown') return true;
	return key === 'ArrowLeft' ? caret.atStart : caret.atEnd;
}

export type GridPosition = { row: number; col: number };

const DELTA: Record<ArrowKey, GridPosition> = {
	ArrowUp: { row: -1, col: 0 },
	ArrowDown: { row: 1, col: 0 },
	ArrowLeft: { row: 0, col: -1 },
	ArrowRight: { row: 0, col: 1 }
};

/** The next cell position for a key press, or null if it would move outside the grid. */
export function nextCellPosition(
	pos: GridPosition,
	key: ArrowKey,
	rowCount: number,
	colCount: number
): GridPosition | null {
	const d = DELTA[key];
	const row = pos.row + d.row;
	const col = pos.col + d.col;
	if (row < 0 || row >= rowCount || col < 0 || col >= colCount) return null;
	return { row, col };
}
