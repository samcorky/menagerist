import { readOptionalFlag, writeFlag } from '$lib/remembered';

export type SidebarMode = 'expanded' | 'rail' | 'drawer';

const RAIL_FROM = 768;
const EXPANDED_FROM = 1280;
const KEY = 'sidebar:expanded';

/** What the sidebar does at a width when the person has not chosen: wide, rail, or a drawer. */
export function defaultMode(width: number): SidebarMode {
	if (width >= EXPANDED_FROM) return 'expanded';
	return width >= RAIL_FROM ? 'rail' : 'drawer';
}

export class SidebarController {
	width = $state(EXPANDED_FROM);
	drawerOpen = $state(false);
	// Whether the person last left the sidebar expanded; unset until they use the burger.
	private expanded = $state<boolean | undefined>(readOptionalFlag(KEY));

	constructor(width: number = EXPANDED_FROM) {
		this.width = width;
	}

	/** A narrow screen always gets the drawer; otherwise the remembered choice, then the default. */
	mode: SidebarMode = $derived.by(() => {
		if (this.width < RAIL_FROM) return 'drawer';
		if (this.expanded === undefined) return defaultMode(this.width);
		return this.expanded ? 'expanded' : 'rail';
	});

	setWidth(width: number) {
		this.width = width;
		if (width >= RAIL_FROM) this.drawerOpen = false;
	}

	/** The burger: opens or closes the drawer, or switches between expanded and rail. */
	toggle() {
		if (this.mode === 'drawer') {
			this.drawerOpen = !this.drawerOpen;
			return;
		}
		this.expanded = this.mode !== 'expanded';
		writeFlag(KEY, this.expanded);
	}

	closeDrawer() {
		this.drawerOpen = false;
	}
}

export const sidebar = new SidebarController(
	typeof window === 'undefined' ? EXPANDED_FROM : window.innerWidth
);
