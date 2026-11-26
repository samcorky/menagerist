import { listNodes, type NodeResponse } from '$lib/api/client';

/** The most rows a list returns in one page. */
export const PAGE_LIMIT = 100;

/** The `after` cursor the Link header's next page carries, or null when there is no next page. */
export function nextCursor(link: string | null | undefined): string | null {
	const next = /<([^>]*)>\s*;\s*rel="next"/.exec(link ?? '');
	const after = next && /[?&]after=([^&#]*)/.exec(next[1]);
	if (!after) return null;
	try {
		return decodeURIComponent(after[1]);
	} catch {
		return null;
	}
}

/**
 * Up to `max` items, a page at a time, following the Link header's cursor. A failed page ends
 * the read with what was loaded, so a screen that only needs names to show still works.
 */
export async function fetchItems(max = 500): Promise<NodeResponse[]> {
	const items: NodeResponse[] = [];
	let after: string | undefined;
	while (items.length < max) {
		const result = await listNodes({ query: { after, limit: PAGE_LIMIT } });
		if (result.error || !result.data) break;
		items.push(...result.data);
		const next = nextCursor(result.response?.headers.get('link'));
		if (next === null) break;
		after = next;
	}
	return items.slice(0, max);
}
