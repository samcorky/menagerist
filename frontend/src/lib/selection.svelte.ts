import { SvelteSet } from 'svelte/reactivity';

/** The most items one bulk action takes; the backend refuses more. */
export const SELECTION_LIMIT = 200;

/**
 * The items picked for a bulk action on one page. The selection outlives a search or filter
 * (so picks from several searches can be acted on together) but not the page, so each page
 * makes its own and drops it with `exit`.
 */
export class Selection {
	active = $state(false);
	readonly #ids = new SvelteSet<string>();

	get ids(): ReadonlySet<string> {
		return this.#ids;
	}

	get count(): number {
		return this.#ids.size;
	}

	get atLimit(): boolean {
		return this.#ids.size >= SELECTION_LIMIT;
	}

	enter(): void {
		this.active = true;
	}

	/** Leave selection mode and forget every pick. Does nothing else. */
	exit(): void {
		this.active = false;
		this.#ids.clear();
	}

	has(id: string): boolean {
		return this.#ids.has(id);
	}

	/** Pick or unpick one item; a pick past the limit is refused. */
	toggle(id: string): void {
		if (this.#ids.has(id)) this.#ids.delete(id);
		else if (!this.atLimit) this.#ids.add(id);
	}

	/** Pick every visible item, as many as fit under the limit. */
	selectAll(visibleIds: string[]): void {
		for (const id of visibleIds) {
			if (this.atLimit) return;
			this.#ids.add(id);
		}
	}

	/** Unpick the visible items; picks the current view hides are kept. */
	deselectAll(visibleIds: string[]): void {
		for (const id of visibleIds) this.#ids.delete(id);
	}

	/** How many picked items are not in `visibleIds`. */
	hiddenCount(visibleIds: string[]): number {
		const visible = new SvelteSet(visibleIds);
		let hidden = 0;
		for (const id of this.#ids) if (!visible.has(id)) hidden += 1;
		return hidden;
	}

	/** Forget every pick but stay in selection mode. */
	clear(): void {
		this.#ids.clear();
	}

	/** Forget the given items, such as ones the server says no longer exist. */
	drop(ids: string[]): void {
		for (const id of ids) this.#ids.delete(id);
	}
}
