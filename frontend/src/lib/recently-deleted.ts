import type { CollectionKind } from '$lib/api/client';

export const NOTHING_DELETED_MESSAGE = 'Nothing has been deleted.';
export const DELETED_PAGE_SIZE = 50;

export type DeletedTab = 'items' | 'collections';

/** "Deleted just now", "Deleted 5 minutes ago", "Deleted 3 days ago". Elapsed time, not calendar days. */
export function describeDeleted(deletedAt: string, now: Date): string {
	const when = new Date(deletedAt);
	if (isNaN(when.getTime())) return 'Deleted';
	const elapsed = now.getTime() - when.getTime();
	if (elapsed < 60_000) return 'Deleted just now';
	const unit = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`;
	const minutes = Math.floor(elapsed / 60_000);
	if (minutes < 60) return `Deleted ${unit(minutes, 'minute')} ago`;
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return `Deleted ${unit(hours, 'hour')} ago`;
	const days = Math.floor(hours / 24);
	if (days < 60) return `Deleted ${unit(days, 'day')} ago`;
	const months = Math.floor(days / 30);
	if (months < 24) return `Deleted ${unit(months, 'month')} ago`;
	return `Deleted ${unit(Math.floor(days / 365), 'year')} ago`;
}

/** The category text for a deleted item: its label if known, else the raw slug, else nothing. */
export function deletedItemType(
	type: string | null | undefined,
	labels: Readonly<Record<string, string>>
): string | null {
	if (!type) return null;
	return labels[type] ?? type;
}

/** The badge for a deleted collection, matching the collections list ("Smart" or "List"). */
export function deletedCollectionBadge(kind: CollectionKind): 'Smart' | 'List' {
	return kind === 'dynamic' ? 'Smart' : 'List';
}

export function purgeDescription(name: string): string {
	return `This permanently deletes ${name}. This cannot be undone.`;
}

/** The `after` cursor for the next page, or null when the Link header has no next page. */
export function nextCursor(
	link: string | null | undefined,
	rows: readonly { id: string }[]
): string | null {
	if (!/rel="next"/.test(link ?? '') || rows.length === 0) return null;
	return rows[rows.length - 1].id;
}

/** A plain message for a failed restore or purge, keeping the server's wording for a 409. */
export function deletedActionError(
	action: 'restore' | 'purge',
	status: number | undefined,
	detail: string
): string {
	if (status === 409 && detail) return detail;
	if (status === 404) return 'This has already been removed. Reload the page to refresh the list.';
	if (status === 403) return `You do not have permission to ${action} this.`;
	if (status === undefined) return 'You appear to be offline. Check your connection and try again.';
	return `Could not ${action} this. Try again.`;
}

/** Rows whose name contains `query`, ignoring case and surrounding space; all rows when empty. */
export function filterByName<T extends { name: string }>(rows: readonly T[], query: string): T[] {
	const needle = query.trim().toLowerCase();
	return needle ? rows.filter((r) => r.name.toLowerCase().includes(needle)) : [...rows];
}
