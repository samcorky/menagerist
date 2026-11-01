import { withFilter } from '$lib/query/items-page';
import type { Condition, Group, Node, Query } from '$lib/query/types';

/** The query language lists at most this many ids in one condition (backend graph/domain/query.py). */
export const TIDY_LIST_LIMIT = 50;

const all = (...children: Node[]): Group => ({ op: 'and', children });
const where = (...children: Node[]): Query => ({ v: 1, where: all(...children), sort: [] });

/** Newest first: the item list itself has no such order, so Home asks the search endpoint. */
export const newestQuery = (): Query => ({
	v: 1,
	where: null,
	sort: [{ by: 'created', dir: 'desc' }]
});

export const editedQuery = (): Query => ({
	v: 1,
	where: null,
	sort: [{ by: 'updated', dir: 'desc' }]
});

/** Every item: counting it gives the exact total. */
export const everythingQuery = (): Query => ({ v: 1, where: null, sort: [] });

export const favouriteQuery = (): Query => where({ kind: 'favourite', value: true });

/** Items created in the last 30 days. */
export const monthQuery = (): Query =>
	where({ kind: 'date', on: 'created', op: '>=', value: { rel: '-30d' } });

export const photoQuery = (): Query => where({ kind: 'media', mode: 'has' });
export const noPhotoQuery = (): Query => where({ kind: 'media', mode: 'none' });
export const noDescriptionQuery = (): Query => where({ kind: 'description', op: 'empty' });

const fits = (list: string[]) => list.length > 0 && list.length <= TIDY_LIST_LIMIT;

/**
 * Items on none of the collections. The language names collections by id, so this is only
 * askable while they all fit in one condition; otherwise null and the row is left out.
 */
export function notInCollectionQuery(collectionIds: string[]): Query | null {
	if (!fits(collectionIds)) return null;
	return where({ kind: 'collection', mode: 'none', in: collectionIds } satisfies Condition);
}

/** Items whose type is none of the item types (no type at all); null as above. */
export function noTypeQuery(typeSlugs: string[]): Query | null {
	if (!fits(typeSlugs)) return null;
	return where({ op: 'not', children: [{ kind: 'type', in: typeSlugs }] });
}

export type TidyRow = { id: string; label: string; query: Query };

/** The tidy-up rows that can be counted accurately for this library. */
export function tidyRows(args: { collectionIds: string[]; typeSlugs: string[] }): TidyRow[] {
	const rows: (TidyRow | null)[] = [
		{ id: 'no-photo', label: 'No photo', query: noPhotoQuery() },
		{ id: 'no-description', label: 'No description', query: noDescriptionQuery() }
	];
	const noCollection = notInCollectionQuery(args.collectionIds);
	rows.push(
		noCollection && { id: 'no-collection', label: 'Not in any collection', query: noCollection }
	);
	const noType = noTypeQuery(args.typeSlugs);
	rows.push(noType && { id: 'no-type', label: 'No item type', query: noType });
	return rows.filter((row): row is TidyRow => row !== null);
}

/** The Items page opened on exactly this filter, so its list matches the dashboard count. */
export function itemsHref(query: Query): string {
	const params = withFilter(new URLSearchParams(), query);
	const search = params.toString();
	return search ? `/items?${search}` : '/items';
}

export function greeting(hour: number): string {
	if (hour >= 5 && hour < 12) return 'Good morning';
	if (hour >= 12 && hour < 18) return 'Good afternoon';
	return 'Good evening';
}

/** A whole-number share, 0 with nothing to divide by and never above 100. */
export function percent(part: number, total: number): number {
	if (total <= 0) return 0;
	return Math.min(100, Math.round((part / total) * 100));
}
