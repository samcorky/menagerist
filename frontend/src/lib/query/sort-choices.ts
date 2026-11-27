import type { NodeSort, SortOrder } from '$lib/api/client';
import type { Query, SortKey } from '$lib/query/types';

/** One of the orders the Items toolbar offers: a name for it and the sort it writes. */
export interface SortChoice {
	value: string;
	label: string;
	sort: SortKey[];
}

/**
 * The common orders for the Items list. They are the same `sort` the Filters dialog edits, so
 * the toolbar and the dialog never disagree. "Oldest first" is no sort at all: the plain list,
 * which comes in creation order.
 */
export const SORT_CHOICES: readonly SortChoice[] = [
	{ value: 'oldest', label: 'Oldest first', sort: [] },
	{ value: 'newest', label: 'Newest first', sort: [{ by: 'created', dir: 'desc' }] },
	{ value: 'updated', label: 'Recently updated', sort: [{ by: 'updated', dir: 'desc' }] },
	{ value: 'name-asc', label: 'Name A to Z', sort: [{ by: 'name', dir: 'asc' }] },
	{ value: 'name-desc', label: 'Name Z to A', sort: [{ by: 'name', dir: 'desc' }] }
];

/** The value for a sort that is none of the choices, such as one built in the Filters dialog. */
export const CUSTOM_SORT = 'custom';

const describe = (sort: readonly SortKey[]) =>
	sort.map((k) => `${k.by}:${k.dir ?? 'asc'}:${k.type ?? ''}:${k.key ?? ''}`).join('|');

/** Which choice `sort` is, or `CUSTOM_SORT`. A key with no direction sorts ascending. */
export function sortChoiceOf(sort: readonly SortKey[]): string {
	return SORT_CHOICES.find((c) => describe(c.sort) === describe(sort))?.value ?? CUSTOM_SORT;
}

/** `query` with the sort of the choice `value`; unchanged for a value that is not one. */
export function withSortChoice(query: Query, value: string): Query {
	const choice = SORT_CHOICES.find((c) => c.value === value);
	return choice ? { ...query, sort: choice.sort.map((key) => ({ ...key })) } : query;
}

/** The value for "as the collection saved it", the first choice on a smart collection's page. */
export const SAVED_SORT = 'saved';

const NODE_SORT = { name: 'name', created: 'created_at', updated: 'updated_at' } as const;

/**
 * The `sort` and `order` the item list route takes for `sort`; nothing for no sort, and a key
 * of a field is left out, since only the search route sorts by those.
 */
export function nodeSortParams(sort: readonly SortKey[]): {
	sort?: NodeSort[];
	order?: SortOrder[];
} {
	const keys = sort.filter((key) => key.by !== 'field');
	if (keys.length === 0) return {};
	return {
		sort: keys.map((key) => NODE_SORT[key.by as keyof typeof NODE_SORT]),
		order: keys.map((key) => key.dir ?? 'asc')
	};
}

/** The choice named `value`, or undefined for a value that is none. */
export function sortChoiceByValue(value: string | null | undefined): SortChoice | undefined {
	return SORT_CHOICES.find((choice) => choice.value === value);
}
