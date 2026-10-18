export const MAX_COLLECTION_NAME_LENGTH = 120;

/** "No items", "1 item", "12 items". */
export function describeItemCount(count: number): string {
	if (count === 0) return 'No items';
	return `${count} ${count === 1 ? 'item' : 'items'}`;
}

/** The toast after adding items: how many went on and how many were already there. */
export function describeAddResult(added: number, requested: number): string {
	if (added === 0)
		return requested === 1 ? 'That item is already there' : 'Those items are already there';
	const skipped = requested - added;
	const base = `Added ${added} ${added === 1 ? 'item' : 'items'}`;
	return skipped > 0 ? `${base}. ${skipped} ${skipped === 1 ? 'was' : 'were'} already there` : base;
}

/** Friendly error text when items cannot be added. */
export function addItemsErrorMessage(status: number | undefined): string {
	if (status === 400) return 'Some of those items no longer exist. Refresh and try again.';
	if (status === 404) return 'This collection no longer exists.';
	if (status === 422) return 'You can add up to 500 items at a time.';
	return "Couldn't add those items. Try again.";
}

/** Client-side hint for a collection name; the server still has the last word. */
export function validateCollectionName(name: string): string | null {
	const trimmed = name.trim();
	if (trimmed.length === 0) return 'Give the collection a name.';
	if (trimmed.length > MAX_COLLECTION_NAME_LENGTH)
		return `Names can be up to ${MAX_COLLECTION_NAME_LENGTH} characters.`;
	return null;
}

/** A friendly message when creating or renaming fails. */
export function collectionSaveErrorMessage(status: number | undefined): string {
	if (status === 400 || status === 422) return 'That name is not valid. Use 1 to 120 characters.';
	if (status === 409) return 'A collection with that link name already exists.';
	if (status === 404) return 'This collection no longer exists.';
	return "Couldn't save the collection. Try again.";
}

const UUID_PATTERN = /^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$/i;

/**
 * The route parameters of a collection's page; links use the slug, except for an old slug that
 * reads as an id (the server would take it for one), which falls back to the id.
 */
export function collectionRouteParams(collection: { id?: string; slug: string }): { id: string } {
	if (collection.id && UUID_PATTERN.test(collection.slug)) return { id: collection.id };
	return { id: collection.slug };
}

/**
 * The slug the address should be replaced with, or null when it already is the slug (or the
 * collection has not loaded). Covers an address that holds the id or a slug that was renamed.
 */
export function canonicalSlugFor(
	segment: string,
	collection: { slug: string } | null
): string | null {
	if (!collection || segment === collection.slug) return null;
	return collection.slug;
}

/** The slug part of an update: the typed slug when it changed, otherwise nothing. */
export function slugPatch(current: string, typed: string): { slug?: string } {
	const slug = typed.trim();
	return slug === current ? {} : { slug };
}

/** The inline message for a rejected slug, or null when the failure is not about the slug. */
export function slugSaveErrorMessage(status: number | undefined, detail: string): string | null {
	if (status === 409) return 'That link is already used by another collection.';
	if (status === 400) return detail || 'That link is not valid.';
	return null;
}

/**
 * A collection's address (pathname form, for `resolve()`) with a query string and hash carried
 * over; the slug is always used, never the id.
 */
export function collectionAddress(
	collection: { slug: string },
	location: { search: string; hash: string }
): `/collections/${string}` {
	return `/collections/${encodeURIComponent(collection.slug)}${location.search}${location.hash}`;
}
