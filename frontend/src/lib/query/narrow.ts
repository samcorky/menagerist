import { fitsLimits } from './limits';
import { combinePrefix, formatCount } from './items-page';
import { combine, countConditions, searchTextTooLong } from './tree';
import { parseQueryPath, pathKey, toFilterPath, type WarningMarks } from './warnings';
import type { Group, Node, Path, Query } from './types';

/*
 * Ad-hoc narrowing of a smart collection: what a person adds on the collection page (the
 * Filter button, the search box, the type select) is ANDed onto the saved conditions. The
 * saved definition itself is never changed by this.
 */

/** The search box and the type select, as on the items page. */
export type NarrowBasics = { q?: string; type?: string | null };

const nodesOf = (group: Group | null): Node[] =>
	!group ? [] : group.op === 'and' ? group.children : [group];

const asPageBasics = (basics: NarrowBasics) => ({ q: basics.q ?? '', type: basics.type ?? null });

/** Merge saved filters with ad-hoc ones and keep the saved sort by default. */
export function combineWithSaved(saved: Query, adhoc: Query, basics: NarrowBasics = {}): Query {
	const extra = combine(adhoc, basics).where;
	const sort = adhoc.sort.length > 0 ? adhoc.sort : saved.sort;
	const added = nodesOf(extra);
	if (added.length === 0) return { ...saved, sort };
	const kept = nodesOf(saved.where);
	if (kept.length === 0) return { v: saved.v, where: extra, sort };
	return { v: saved.v, where: { op: 'and', children: [...kept, ...added] }, sort };
}

/** How many filters the person added: ad-hoc conditions, plus the search text and the type. */
export function narrowFilterCount(adhoc: Query, basics: NarrowBasics): number {
	return countConditions(adhoc) + (basics.q?.trim() ? 1 : 0) + (basics.type ? 1 : 0);
}

/** Decide whether the saved and ad-hoc searches need to be combined. */
export function needsNarrowing(adhoc: Query, basics: NarrowBasics): boolean {
	return narrowFilterCount(adhoc, basics) > 0 || adhoc.sort.length > 0;
}

/** "Narrowed by 2 filters: 3 of 12 items"; the counts are left out until the results are in. */
export function narrowedBarText(
	filters: number,
	shown: { total: number; capped: boolean } | null,
	own: { count: number; capped: boolean }
): string {
	const lead =
		filters === 0
			? 'Sorted differently'
			: `Narrowed by ${filters} ${filters === 1 ? 'filter' : 'filters'}`;
	if (!shown) return lead;
	const noun = own.count === 1 && !own.capped ? 'item' : 'items';
	return `${lead}: ${formatCount(shown.total, shown.capped)} of ${formatCount(own.count, own.capped)} ${noun}`;
}

export const NARROW_TOO_LARGE_MESSAGE =
	'Too many conditions to search with the saved ones. Remove a filter.';
export const SAVE_TOO_LARGE_MESSAGE =
	'The saved conditions and your filters together are too large to save. Remove a filter to save them.';
export const SAVE_TEXT_TOO_LONG_MESSAGE =
	'The search text is too long to save as a condition. Shorten it to 200 characters.';

/** Why the combined conditions cannot be saved, or null when they can. */
export function saveBlockReason(saved: Query, adhoc: Query, basics: NarrowBasics): string | null {
	if (searchTextTooLong(basics.q)) return SAVE_TEXT_TOO_LONG_MESSAGE;
	return fitsLimits(combineWithSaved(saved, adhoc, basics)) ? null : SAVE_TOO_LARGE_MESSAGE;
}

const conditions = (n: number) => `${n} ${n === 1 ? 'condition' : 'conditions'}`;

/** What "Update this collection" will do, for the confirmation. */
export function updateConfirmation(before: number, after: number, replacesSort = false): string {
	const sort = replacesSort ? ' and replaces the sort' : '';
	return `This replaces the collection's ${conditions(before)} with ${conditions(after)}: the current ones plus your filters${sort}. Items that don't match will leave this collection.`;
}

/**
 * Where a path in the combined tree sent to the server belongs: the saved conditions or the
 * ad-hoc filter (as the builder shows it). Null for the root and for conditions added for the
 * search box or the type select.
 */
export function locateInCombined(
	path: Path,
	saved: Query,
	adhoc: Query,
	basics: NarrowBasics
): { part: 'saved' | 'adhoc'; path: Path } | null {
	const extra = combine(adhoc, basics).where;
	const keptCount = nodesOf(saved.where).length;

	const adhocPath = (inExtra: Path): Path | null => {
		if (!adhoc.where || inExtra.length === 0) return null;
		// A flat and-root may be followed by the conditions added for the search box
		if (
			extra?.op === 'and' &&
			adhoc.where.op === 'and' &&
			inExtra[0] >= adhoc.where.children.length
		)
			return null;
		return toFilterPath(inExtra, combinePrefix(adhoc, asPageBasics(basics)));
	};

	if (nodesOf(extra).length === 0) return path.length > 0 ? { part: 'saved', path } : null;
	if (keptCount === 0) {
		const inAdhoc = adhocPath(path);
		return inAdhoc ? { part: 'adhoc', path: inAdhoc } : null;
	}
	if (path.length === 0) return null;
	const [first, ...rest] = path;
	if (first < keptCount) {
		if (saved.where?.op === 'and') return { part: 'saved', path };
		return rest.length > 0 ? { part: 'saved', path: rest } : null;
	}
	const index = first - keptCount;
	const inExtra = extra?.op === 'and' ? [index, ...rest] : index === 0 ? rest : null;
	const inAdhoc = inExtra ? adhocPath(inExtra) : null;
	return inAdhoc ? { part: 'adhoc', path: inAdhoc } : null;
}

/** The warnings that belong to the ad-hoc filter, as marks on its own conditions. */
export function narrowedMarks(
	warnings: { path: string; message?: string }[],
	saved: Query,
	adhoc: Query,
	basics: NarrowBasics
): WarningMarks {
	const marks: WarningMarks = { conditions: new Set(), sort: false };
	for (const { path } of warnings) {
		const target = parseQueryPath(path);
		if (!target) continue;
		if ('sort' in target) {
			marks.sort = true;
			continue;
		}
		const at = locateInCombined(target.where, saved, adhoc, basics);
		if (at?.part === 'adhoc') marks.conditions.add(pathKey(at.path));
	}
	return marks;
}

export const LINKED_TOO_LARGE_MESSAGE =
	'Too many conditions to link this to the collection. Remove a filter to save it.';

/**
 * The conditions for "Save as new, linked to this collection": `in collection <parent>` ANDed
 * with the ad-hoc filters (and the page's search text and type, as in `combineWithSaved`).
 * The parent's own conditions are not copied. Null when the result would break a limit.
 */
export function linkedNarrow(
	parentId: string,
	adhoc: Query,
	basics: NarrowBasics = {}
): Query | null {
	const linked: Query = {
		v: 1,
		where: {
			op: 'and',
			children: [
				{ kind: 'collection', mode: 'any', in: [parentId] },
				...nodesOf(combine(adhoc, basics).where)
			]
		},
		sort: adhoc.sort
	};
	return fitsLimits(linked) ? linked : null;
}

/** Why the linked collection cannot be saved, or null when it can. */
export function linkedBlockReason(
	parentId: string,
	adhoc: Query,
	basics: NarrowBasics
): string | null {
	if (searchTextTooLong(basics.q)) return SAVE_TEXT_TOO_LONG_MESSAGE;
	return linkedNarrow(parentId, adhoc, basics) ? null : LINKED_TOO_LARGE_MESSAGE;
}
