import { untrack } from 'svelte';
import { applyDraft, blankCondition, conditionNumbers, groupAt, queryKey } from './builder';
import type { Catalogue } from './fields';
import { canAddCondition, canAddGroup } from './limits';
import { addCondition, addGroup, emptyQuery, removeAt, replaceAt } from './tree';
import { pathKey } from './warnings';
import type { Condition, Path, Query, SortKey } from './types';

/**
 * The filter builder's draft and its edits. The draft may hold unfinished rows; each edit
 * passes the runnable part to `onchange`, and only when it differs from what was sent last.
 */
export class BuilderState {
	draft = $state<Query>(emptyQuery());
	/** What the panel shows: an empty filter gets one row to fill in. */
	shown = $derived(this.draft.where ? this.draft : addCondition(this.draft, [], blankCondition()));
	#lastKey: string;
	#catalogue: () => Catalogue;
	#onchange: (query: Query, options: { debounce: boolean }) => void;

	constructor(
		query: Query,
		catalogue: () => Catalogue,
		onchange: (query: Query, options: { debounce: boolean }) => void
	) {
		this.draft = query;
		this.#lastKey = queryKey(query);
		this.#catalogue = catalogue;
		this.#onchange = onchange;
	}

	/** Follow the applied filter when it changes from elsewhere (Back, a chip removed). */
	sync(query: Query): void {
		const key = queryKey(query);
		if (key === this.#lastKey) return;
		this.#lastKey = key;
		this.draft = query;
	}

	commit(next: Query, debounce = false): void {
		this.draft = next;
		const applied = applyDraft(next, untrack(this.#catalogue)).query;
		const key = queryKey(applied);
		if (key === this.#lastKey) return;
		this.#lastKey = key;
		this.#onchange(applied, { debounce });
	}

	update(path: Path, condition: Condition, debounce = false): void {
		this.commit(replaceAt(this.shown, path, condition), debounce);
	}

	/** Remove a row or group; returns the removed row's number, if it was a row. */
	remove(path: Path): number | undefined {
		const n = conditionNumbers(this.shown).get(pathKey(path));
		this.commit(removeAt(this.shown, path));
		return n;
	}

	#childCount(groupPath: Path): number {
		return groupAt(this.shown, groupPath)?.children.length ?? 0;
	}

	/** Add a blank row to a group; returns its path, or null at the limit. */
	addCondition(groupPath: Path): Path | null {
		if (!canAddCondition(this.shown)) return null;
		const at = [...groupPath, this.#childCount(groupPath)];
		this.commit(addCondition(this.shown, groupPath, blankCondition()));
		return at;
	}

	/** Add an "any" group holding one blank row; returns the row's path, or null at a limit. */
	addGroup(groupPath: Path): Path | null {
		if (!canAddCondition(this.shown) || !canAddGroup(this.shown, groupPath)) return null;
		const at = [...groupPath, this.#childCount(groupPath)];
		this.commit(addCondition(addGroup(this.shown, groupPath, 'or'), at, blankCondition()));
		return [...at, 0];
	}

	setGroupOp(path: Path, op: 'and' | 'or'): void {
		const group = groupAt(this.shown, path);
		if (!group || group.op === op) return;
		this.commit(replaceAt(this.shown, path, { op, children: group.children }));
	}

	setSort(sort: SortKey[]): void {
		this.commit({ ...this.shown, sort });
	}

	clear(): void {
		this.commit(emptyQuery());
	}
}
