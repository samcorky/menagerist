// How many pages of this app sit behind the current one. Back only goes back when there is one:
// `history.length` also counts pages from before the app was opened (another site, the launcher),
// where going back would leave Menagerist altogether.

let depth = 0;
let skipNext = false;

type Arrival = {
	type: 'enter' | 'form' | 'leave' | 'link' | 'goto' | 'popstate';
	from: { url: { pathname: string } } | null;
	to: { url: { pathname: string } } | null;
	delta?: number;
};

/** Record a finished navigation. Same-page changes (filters, sheets) do not add a page. */
export function noteArrival({ type, from, to, delta }: Arrival): void {
	if (skipNext) {
		skipNext = false;
		return;
	}
	if (type === 'enter') depth = 0;
	else if (!from || !to || from.url.pathname === to.url.pathname) return;
	else if (type === 'popstate') depth = Math.max(0, depth + (delta ?? 0));
	else if (type !== 'leave') depth += 1;
}

/** The next navigation replaces the current entry (a redirect), so it adds no page behind it. */
export function replaceNext(): void {
	skipNext = true;
}

export function canGoBackInApp(): boolean {
	return depth > 0;
}

/** Test seam: forget everything, as a fresh page load does. */
export function resetInAppHistory(): void {
	depth = 0;
	skipNext = false;
}
