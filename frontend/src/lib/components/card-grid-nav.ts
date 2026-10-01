export type NavKey = 'ArrowUp' | 'ArrowDown' | 'ArrowLeft' | 'ArrowRight';

export type CardRect = { top: number; left: number };

/**
 * Given the on-screen position of every card in document order and the
 * index of the one currently focused, returns the index to move focus to
 * for an arrow key press, or null if there's nowhere to go.
 *
 * List mode only moves along Up/Down (one column, no geometry needed).
 * Grid mode moves Left/Right in document order, and Up/Down to the card in
 * the adjacent row whose left offset is closest to the current card's -
 * the column count is responsive, so this reads it from layout instead of
 * assuming a fixed number of columns.
 */
export function nextCardIndex(
	key: NavKey,
	currentIndex: number,
	rects: CardRect[],
	mode: 'list' | 'grid'
): number | null {
	if (currentIndex < 0 || currentIndex >= rects.length) return null;

	if (mode === 'list') {
		if (key === 'ArrowDown') return currentIndex < rects.length - 1 ? currentIndex + 1 : null;
		if (key === 'ArrowUp') return currentIndex > 0 ? currentIndex - 1 : null;
		return null;
	}

	if (key === 'ArrowRight') return currentIndex < rects.length - 1 ? currentIndex + 1 : null;
	if (key === 'ArrowLeft') return currentIndex > 0 ? currentIndex - 1 : null;

	const current = rects[currentIndex];
	const forward = key === 'ArrowDown';
	const rowCandidates = rects
		.map((r, i) => ({ r, i }))
		.filter(({ r }) => (forward ? r.top > current.top : r.top < current.top));
	if (rowCandidates.length === 0) return null;

	const nextRowTop = forward
		? Math.min(...rowCandidates.map(({ r }) => r.top))
		: Math.max(...rowCandidates.map(({ r }) => r.top));

	const sameRow = rowCandidates.filter(({ r }) => r.top === nextRowTop);
	sameRow.sort((a, b) => Math.abs(a.r.left - current.left) - Math.abs(b.r.left - current.left));
	return sameRow[0].i;
}
