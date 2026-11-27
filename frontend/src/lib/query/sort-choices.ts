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
