import type { SortOrder } from '$lib/api/client';

/**
 * How a table is sorted: the key of one column and its direction, or null for the order the
 * server sends. The server does the sorting (`sort` and `order` on the list route), so a table
 * that pages sorts every page, not the one on screen.
 */
export interface TableSort<K extends string = string> {
	key: K;
	order: SortOrder;
}

/**
 * The sort after a click on a column's header: a new column sorts ascending, a second click
 * on it descending, a third goes back to the server's own order.
 */
export function nextSort<K extends string>(
	current: TableSort<K> | null,
	key: K
): TableSort<K> | null {
	if (current?.key !== key) return { key, order: 'asc' };
	return current.order === 'asc' ? { key, order: 'desc' } : null;
}

/** The `sort` and `order` query parameters for a list route; none for the server's own order. */
export function sortQuery<K extends string>(
	sort: TableSort<K> | null
): { sort?: K[]; order?: SortOrder[] } {
	return sort ? { sort: [sort.key], order: [sort.order] } : {};
}

/** The `aria-sort` of a column's header. */
export function ariaSort(sort: TableSort | null, key: string): 'ascending' | 'descending' | 'none' {
	if (sort?.key !== key) return 'none';
	return sort.order === 'asc' ? 'ascending' : 'descending';
}
