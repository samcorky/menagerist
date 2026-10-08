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

/** A friendly message when adding items fails; the server says 400 for items that no longer exist. */
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
