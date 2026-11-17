import type { SidebarMode } from '$lib/sidebar.svelte';

/**
 * Whether the top bar shows the account menu. The sidebar's footer carries it whenever the
 * sidebar is on screen; the top bar keeps it while the sidebar is a closed drawer, and when
 * there is no sidebar at all (an expired password), so Sign out is always one tap away.
 */
export function accountMenuInTopBar(state: { sidebarShown: boolean; mode: SidebarMode }): boolean {
	return !state.sidebarShown || state.mode === 'drawer';
}
