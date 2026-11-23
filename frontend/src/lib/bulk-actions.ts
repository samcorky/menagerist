const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g;

/**
 * The ids a batch request named as missing. The server fails the whole batch with
 * "Unknown or deleted items: <ids>", so the page can drop those and reload.
 */
export function unknownItemIds(detail: string | undefined): string[] {
	if (!detail?.startsWith('Unknown or deleted items')) return [];
	return detail.match(UUID) ?? [];
}

/** "3 items" or "1 item". */
export function itemCount(count: number): string {
	return `${count} ${count === 1 ? 'item' : 'items'}`;
}

/** Split typed tags on commas, trimmed, dropping blanks and repeats (the server lowercases). */
export function parseTagInput(text: string): string[] {
	return [
		...new Set(
			text
				.split(',')
				.map((t) => t.trim())
				.filter(Boolean)
		)
	];
}
