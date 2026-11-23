import type { OnNavigate } from '@sveltejs/kit';

type NavigationEnd = { route: { id: string | null }; url: { pathname: string } } | null;

/**
 * Whether a navigation gets the page-change view transition.
 *
 * A `goto` that stays on the same route is a page rewriting its own address (a collection's
 * id replaced by its slug, filters written to the query string). Animating it would fade the
 * whole page and, while the transition runs, swallow clicks. Back and Forward between two
 * states of the same page (a narrowed list and the plain one) are the same.
 */
export function animatesNavigation(navigation: {
	type: OnNavigate['type'];
	from: NavigationEnd;
	to: NavigationEnd;
}): boolean {
	const from = navigation.from?.route.id;
	const to = navigation.to?.route.id;
	if (navigation.type === 'goto') return !(from && to && from === to);
	if (navigation.type === 'popstate')
		return navigation.from?.url.pathname !== navigation.to?.url.pathname;
	return true;
}

/** The destinations the nav bar and sidebar switch between: peers, not steps in a journey. */
const TOP_LEVEL_PATHS = new Set(['/', '/items', '/collections', '/settings']);

/**
 * How the page change should move. Back through history slides the way the user went; opening a
 * top-level destination from the nav is a switch between peers, so it only fades, as left and
 * right would imply an order they do not have. Every other navigation, Forward included, is a
 * step on.
 */
export function navigationDirection(navigation: {
	type: OnNavigate['type'];
	delta?: number;
	to?: { url: { pathname: string } } | null;
}): 'forward' | 'back' | 'fade' {
	if (navigation.type === 'popstate') return (navigation.delta ?? 0) < 0 ? 'back' : 'forward';
	return TOP_LEVEL_PATHS.has(navigation.to?.url.pathname ?? '') ? 'fade' : 'forward';
}
