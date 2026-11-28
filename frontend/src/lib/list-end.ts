/**
 * The wording and paging rules for the bottom of an infinite list (#588).
 *
 * A list's foot says one of four things: nothing yet, "Loading more…", the end
 * of the list, or that the next page failed and can be retried. The end state
 * carries the factual count, and may add one of the page's own flavour lines in
 * the spirit of the empty-state lines (#102). Errors stay plain (design §11).
 */

import { pickEmptyLine } from '$lib/empty-lines';

/** What the foot of a list is currently saying. */
export type ListEndState = 'idle' | 'loading' | 'end' | 'failed';

/**
 * How far before the list's foot the next page starts loading.
 *
 * The old 200px rarely hid the request: a page of rows is taller than that, so
 * a steady scroller reached the spinner before the rows arrived. A viewport and
 * a half was better, but a quick scroll or a slow connection still caught up with
 * it. Two and a half buys a couple of screens of reading while the page is in
 * flight, and is still no further than the next page, so the first scroll does not
 * fetch pages nobody reads.
 */
export const LOAD_AHEAD_SCREENS = 2.5;

export function loadAheadMargin(viewportHeight: number): string {
	const height = Number.isFinite(viewportHeight) && viewportHeight > 0 ? viewportHeight : 800;
	return `${Math.round(height * LOAD_AHEAD_SCREENS)}px`;
}

/**
 * The nearest ancestor that scrolls, or null when the page itself does.
 *
 * An observer rooted at the viewport ignores its margin for a target inside a scrolling
 * container: the container clips the target first, so the page would load only when the
 * foot is already on screen. The app's pages scroll inside one (`#main-scroll`), so the
 * observer needs it as its root for the margin to count.
 */
export function scrollParent(node: HTMLElement): HTMLElement | null {
	for (let up = node.parentElement; up; up = up.parentElement) {
		const { overflowY } = getComputedStyle(up);
		if (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') return up;
	}
	return null;
}

/** Decides what the foot of a list should show. */
export function listEndState(paging: {
	loading: boolean;
	hasMore: boolean;
	failed: boolean;
	rows: number;
}): ListEndState {
	if (paging.failed) return 'failed';
	if (paging.loading) return paging.rows > 0 ? 'loading' : 'idle';
	// An empty list has its own empty state to speak for it (design §11).
	if (paging.hasMore || paging.rows === 0) return 'idle';
	return 'end';
}

/** "1,204 items", or "1,204 collections" for whatever the list holds. */
export function countedEnd(rows: number, total: number | null, noun: string): string {
	const counted = total ?? rows;
	const plural = counted === 1 ? noun : `${noun}s`;
	return `${counted.toLocaleString('en-GB')} ${plural}`;
}

/** The whole end-of-list sentence: the count, after a flavour line where there is one. */
export function endMessage(
	rows: number,
	total: number | null,
	noun: string,
	lines: readonly string[],
	key: string
): string {
	const counted = countedEnd(rows, total, noun);
	// A short list ends in plain sight; a line there would be noise.
	if (lines.length === 0 || rows < 20) return `That's everything - ${counted}.`;
	return `${pickEmptyLine(lines, key)} ${counted} in all.`;
}

/**
 * Where a table's page sits in its list: "26–50 of 312 sessions", or "26–50 sessions" when
 * the server sent no count. A list that fits one page says how many it holds, as the end of
 * an infinite list does.
 */
export function pageRangeMessage(
	from: number,
	to: number,
	total: number | null,
	noun: string,
	single: boolean
): string {
	if (single) return countedEnd(to, total, noun);
	const range = `${from.toLocaleString('en-GB')}–${to.toLocaleString('en-GB')}`;
	if (total === null) return `${range} ${noun}s`;
	return `${range} of ${total.toLocaleString('en-GB')} ${total === 1 ? noun : `${noun}s`}`;
}

/** The plain line for a next page that would not load. Never a flavour line (design §11). */
export const LOAD_MORE_FAILED = "We couldn't load any more.";
