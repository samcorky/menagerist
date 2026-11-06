// The app scrolls inside #main-scroll, not the window, so SvelteKit's own scroll reset and
// restoration never apply. These helpers do the same job for that container: remember where each
// address was left, restore it on Back/Forward, and start at the top (or a #fragment) otherwise.

type Scroller = Pick<HTMLElement, 'scrollTop' | 'scrollHeight' | 'clientHeight'>;

const positions = new Map<string, number>();

export const scrollKey = (url: Pick<URL, 'pathname' | 'search'>) => url.pathname + url.search;

export function savePosition(url: Pick<URL, 'pathname' | 'search'>, top: number): void {
	positions.set(scrollKey(url), top);
}

export function savedPosition(url: Pick<URL, 'pathname' | 'search'>): number | undefined {
	return positions.get(scrollKey(url));
}

/** Whether a navigation moves to a different page, as opposed to rewriting the current one's query. */
export function changesPage(from: Pick<URL, 'pathname'> | undefined, to: Pick<URL, 'pathname'>) {
	return from?.pathname !== to.pathname;
}

/**
 * Scrolls to `top`, retrying while the content is still loading and too short to reach it.
 *
 * Gives up after `timeout` ms, or as soon as the person scrolls themselves. Returns a cancel
 * function.
 */
export function restoreScroll(el: Scroller & HTMLElement, top: number, timeout = 2000): () => void {
	let frame = 0;
	let stopped = false;
	const started = performance.now();
	let last = -1;
	const step = () => {
		if (stopped) return;
		// A position that differs from the one we last set means the person has scrolled.
		if (last !== -1 && Math.abs(el.scrollTop - last) > 1) return;
		el.scrollTop = top;
		last = el.scrollTop;
		const reachable = el.scrollHeight - el.clientHeight >= top;
		if (reachable || performance.now() - started > timeout) return;
		frame = requestAnimationFrame(step);
	};
	step();
	return () => {
		stopped = true;
		cancelAnimationFrame(frame);
	};
}

/** Scrolls to the element a fragment names; falls back to the top when there is none. */
export function scrollToFragment(el: HTMLElement, hash: string): void {
	const id = decodeURIComponent(hash.replace(/^#/, ''));
	const target = id ? el.ownerDocument.getElementById(id) : null;
	if (target) target.scrollIntoView();
	else el.scrollTop = 0;
}

export function clearPositions(): void {
	positions.clear();
}
