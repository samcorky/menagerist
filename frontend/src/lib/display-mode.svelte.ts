/**
 * Whether the app runs as the installed app (a standalone window) or in a browser tab, following
 * changes as they happen. Layout that differs between the two reads `displayMode.standalone`, or
 * uses `@media (display-mode: standalone)` in CSS. The API client sends the mode with each request
 * (`X-Client-Display-Mode`) so the devices list can say "installed app".
 */

import type { DisplayMode } from '$lib/api/client';

export const DISPLAY_MODE_HEADER = 'X-Client-Display-Mode';

const STANDALONE_QUERY = '(display-mode: standalone)';

/** The parts of `window` the mode is read from, so tests can pass their own. */
export interface DisplayModeEnvironment {
	matchMedia?: (query: string) => Pick<MediaQueryList, 'matches'>;
	navigator?: { standalone?: boolean };
}

/** Whether `env` is the installed app. `navigator.standalone` covers iOS Safari before 16.4. */
export function readStandalone(env: DisplayModeEnvironment): boolean {
	if (env.matchMedia?.(STANDALONE_QUERY).matches) return true;
	return env.navigator?.standalone === true;
}

class DisplayModeController {
	standalone = $state(
		typeof window === 'undefined' ? false : readStandalone(window as DisplayModeEnvironment)
	);

	mode = $derived<DisplayMode>(this.standalone ? 'standalone' : 'browser');

	/** Follow changes of the display mode; returns the cleanup. */
	init(env: Window | undefined = typeof window === 'undefined' ? undefined : window): () => void {
		if (env === undefined || typeof env.matchMedia !== 'function') return () => {};
		const query = env.matchMedia(STANDALONE_QUERY);
		const update = () => (this.standalone = readStandalone(env as DisplayModeEnvironment));
		update();
		query.addEventListener('change', update);
		return () => query.removeEventListener('change', update);
	}
}

export const displayMode = new DisplayModeController();
