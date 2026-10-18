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
