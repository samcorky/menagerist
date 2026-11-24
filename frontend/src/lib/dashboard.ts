import { pickEmptyLine } from '$lib/empty-lines';
import { withFilter } from '$lib/query/items-page';
import type { Group, Node, Query } from '$lib/query/types';

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

/** Items in no collection of the person's own, however many collections there are. */
export const notInCollectionQuery = (): Query => where({ kind: 'collection', mode: 'none' });

/** Items with no item type at all. */
export const noTypeQuery = (): Query => where({ kind: 'type', mode: 'none' });

export type TidyRow = { id: string; label: string; query: Query };

/** The tidy-up rows, each one counted by a single condition that needs no list. */
export function tidyRows(): TidyRow[] {
	return [
		{ id: 'no-photo', label: 'No photo', query: noPhotoQuery() },
		{ id: 'no-description', label: 'No description', query: noDescriptionQuery() },
		{ id: 'no-collection', label: 'Not in any collection', query: notInCollectionQuery() },
		{ id: 'no-type', label: 'No item type', query: noTypeQuery() }
	];
}

/** The Items page opened on exactly this filter, so its list matches the dashboard count. */
export function itemsHref(query: Query): string {
	const params = withFilter(new URLSearchParams(), query);
	const search = params.toString();
	return search ? `/items?${search}` : '/items';
}

const SMALL_HOURS_GREETINGS = [
	'Burning the midnight oil',
	'Up with the owls',
	'Collecting at this hour',
	'The night shift begins'
];

/** The small hours get a session-stable quip; the rest of the day keeps a plain greeting. */
export function greeting(hour: number, seed?: string): string {
	if (hour >= 5 && hour < 12) return 'Good morning';
	if (hour >= 12 && hour < 18) return 'Good afternoon';
	if (hour >= 18) return 'Good evening';
	return pickEmptyLine(SMALL_HOURS_GREETINGS, 'greeting', seed);
}

/** A whole-number share, 0 with nothing to divide by and never above 100. */
export function percent(part: number, total: number): number {
	if (total <= 0) return 0;
	return Math.min(100, Math.round((part / total) * 100));
}

/**
 * `percent` as text. "<1%" when something is there but rounds to nothing, and ">99%" when
 * something is missing but rounds to everything, so neither end reads as none or all.
 */
export function formatPercent(part: number, total: number): string {
	const whole = percent(part, total);
	if (whole === 0 && part > 0 && total > 0) return '<1%';
	if (whole === 100 && part < total) return '>99%';
	return `${whole}%`;
}
