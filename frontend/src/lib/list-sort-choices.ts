import type { CollectionSort } from '$lib/api/client';
import type { TableSort } from '$lib/table-sort';

/** One of the orders a list's "Sort by" select offers: a name for it, and the sort it asks for. */
export interface SortChoice<Key extends string> {
	/** What goes in the address (`?sort=`) and the select's value. */
	value: string;
	label: string;
	/** `null` is the route's own order, which for the lists that offer this is creation order. */
	sort: TableSort<Key> | null;
}

/** The orders the Collections list offers. The first is the route's own order. */
export const COLLECTION_SORT_CHOICES: readonly SortChoice<CollectionSort>[] = [
	{ value: 'oldest', label: 'Oldest first', sort: null },
	{ value: 'newest', label: 'Newest first', sort: { key: 'created_at', order: 'desc' } },
	{ value: 'updated', label: 'Recently updated', sort: { key: 'updated_at', order: 'desc' } },
	{ value: 'name-asc', label: 'Name A to Z', sort: { key: 'name', order: 'asc' } },
	{ value: 'name-desc', label: 'Name Z to A', sort: { key: 'name', order: 'desc' } }
];

/** The choice named `value`, or the first (the route's own order) for a value that is none. */
export function sortChoiceFor<Key extends string>(
	choices: readonly SortChoice<Key>[],
	value: string | null | undefined
): SortChoice<Key> {
	return choices.find((choice) => choice.value === value) ?? choices[0];
}
