// Sheets and dialogs each own one history entry while open (see components/back-layer.svelte), so
// the system Back gesture closes them. One coordinator keeps the number of entries equal to the
// number of open layers, whatever order they open and close in: a dialog that closes as the next
// opens must neither close the new one nor leave an extra entry behind.

import { goto, pushState, replaceState } from '$app/navigation';
import { navigating, page } from '$app/state';

interface Layer {
	onclose: () => void;
}

const stack: Layer[] = [];
// History entries this coordinator believes it holds. A drop below it that it did not cause is
// Back (or a swipe) removing entries.
let known = 0;
let scheduled = false;
let popping: Promise<void> | null = null;
let serial = 0;
// The address each entry was opened on, so a closing layer can tell when the address was rewritten
// while it was open (filters written to the query string). That rewrite lands on the layer's own
// entry, which closing discards.
const openedAt: string[] = [];
// The layers' entries while a navigation that stays on the page runs: SvelteKit clears the page
// state on `goto`, which must not read as Back.
let keeping: string[] | null = null;
let keepTimer: ReturnType<typeof setTimeout> | undefined;

const entries = () => page.state.layers?.length ?? 0;

/**
 * Go back one history entry, resolving once the router has handled it. Callers asking while a
 * pop is already under way share it, so a layer closing and a navigation starting at the same
 * moment remove one entry between them, not two.
 */
export function popLayer(): Promise<void> {
	popping ??= new Promise((resolve) => {
		window.addEventListener(
			'popstate',
			() => {
				popping = null;
				// After the router's own popstate handler has updated the page state.
				setTimeout(resolve, 0);
			},
			{ once: true }
		);
		history.back();
	});
	return popping;
}

/** Remove every open layer's entry, so a navigation that follows adds one entry, not two. */
export async function popAllLayers(): Promise<void> {
	while (entries() > 0) await popLayer();
}

/** An overlay is open: give it a history entry until the returned function is called. */
export function registerLayer(onclose: () => void): () => void {
	const layer: Layer = { onclose };
	stack.push(layer);
	schedule();
	return () => {
		const index = stack.indexOf(layer);
		if (index >= 0) stack.splice(index, 1);
		schedule();
	};
}

/** Close the top layers whose entries Back has removed. Call when the page state changes. */
export function syncLayers(): void {
	if (keeping) return;
	const have = entries();
	if (have >= known) return;
	known = have;
	openedAt.length = Math.min(openedAt.length, have);
	while (stack.length > have) stack.pop()?.onclose();
}

/**
 * Call before a navigation that stays on the same page (a `goto` rewriting the address, such as
 * filters written to the query string). The open layers keep their entries through it.
 */
export function keepLayersThrough(): void {
	const layers = page.state.layers;
	if (!layers?.length) return;
	keeping = layers;
	clearTimeout(keepTimer);
	// A navigation another handler cancels never finishes, so do not wait for it for ever.
	keepTimer = setTimeout(restoreLayers, 1500);
}

/** Put the layers' state back once such a navigation has finished. */
export function restoreLayers(): void {
	clearTimeout(keepTimer);
	const layers = keeping;
	keeping = null;
	if (layers && entries() < layers.length) replaceState('', { layers });
}

function schedule(): void {
	if (scheduled) return;
	scheduled = true;
	// Let a closing layer and an opening one both settle before deciding what to push or pop.
	setTimeout(() => {
		scheduled = false;
		void reconcile();
	}, 0);
}

async function reconcile(): Promise<void> {
	syncLayers();
	if (navigating.to) return schedule();
	const have = entries();
	if (have > stack.length) {
		known = have - 1;
		const current = page.url.href;
		const base = openedAt.pop();
		await popLayer();
		if (base !== undefined && base !== current) await keepAddress(base, current);
		schedule();
	} else if (have < stack.length) {
		openedAt.push(page.url.href);
		pushState('', { layers: [...(page.state.layers ?? []), `layer-${++serial}`] });
		known = have + 1;
		schedule();
	}
}

// Going back returned to the address the layer opened on; put back the one it ended with, as a
// replacement, so a filter applied inside the sheet survives the sheet closing.
async function keepAddress(base: string, wanted: string): Promise<void> {
	for (let waited = 0; page.url.href !== base && waited < 1000; waited += 20) {
		await new Promise((resolve) => setTimeout(resolve, 20));
	}
	if (page.url.href === base) {
		// An address the router already accepted.
		// eslint-disable-next-line svelte/no-navigation-without-resolve
		await goto(wanted, { replaceState: true, noScroll: true, keepFocus: true });
	}
}

/** Test seam: forget every layer, as a fresh page load does. */
export function resetLayers(): void {
	stack.length = 0;
	openedAt.length = 0;
	keeping = null;
	clearTimeout(keepTimer);
	known = 0;
	scheduled = false;
	popping = null;
}
