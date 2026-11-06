// What the service worker may touch. Kept apart from the worker so it can be unit tested.
//
// The worker is for resilience, not offline data: it holds the build's immutable files and one
// offline page, and nothing else. Responses to anything the person did (API calls, sign-in,
// uploads, media, admin pages) are never put in Cache Storage.

export const CACHE_PREFIX = 'menagerist-shell-';
export const OFFLINE_URL = '/offline.html';

/** Extra files the offline page needs, beside the build's own files. */
export const SHELL_FILES = [OFFLINE_URL];

export type Route =
	/** A precached file: answer from Cache Storage. */
	| 'asset'
	/** A page load: ask the network, and show the offline page if it cannot be reached. */
	| 'navigation'
	/** Leave it alone: the browser handles it as if there were no worker. */
	| 'network';

export const cacheName = (version: string) => CACHE_PREFIX + version;

/** The caches of earlier versions, which the new worker deletes when it activates. */
export function staleCaches(names: readonly string[], current: string): string[] {
	return names.filter((name) => name.startsWith(CACHE_PREFIX) && name !== current);
}

export function routeFor(
	request: { method: string; mode: string; url: string },
	origin: string,
	precached: ReadonlySet<string>
): Route {
	if (request.method !== 'GET') return 'network';
	const url = new URL(request.url);
	if (url.origin !== origin) return 'network';
	if (url.pathname === '/api' || url.pathname.startsWith('/api/')) return 'network';
	if (precached.has(url.pathname)) return 'asset';
	return request.mode === 'navigate' ? 'navigation' : 'network';
}
