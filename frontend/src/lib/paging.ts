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

/** What a generated list call resolves to. */
export interface PageResult<T> {
	data?: T[];
	error?: unknown;
	response?: Response;
}

export interface PagesRead<T> {
	rows: T[];
	/** False when a page failed; `rows` then holds what was read before it. */
	ok: boolean;
}

/**
 * Read a list a page at a time, following the Link header's cursor until there is no next page,
 * `maxRows` rows are read, or `maxPages` pages have been.
 */
export async function readPages<T>(
	fetchPage: (after: string | undefined) => Promise<PageResult<T>>,
	{ maxRows = Infinity, maxPages = Infinity } = {}
): Promise<PagesRead<T>> {
	const rows: T[] = [];
	let after: string | undefined;
	for (let page = 0; page < maxPages && rows.length < maxRows; page++) {
		const result = await fetchPage(after);
		if (result.error || !result.data) return { rows, ok: false };
		rows.push(...result.data);
		const next = nextCursor(result.response?.headers.get('link'));
		if (next === null) break;
		after = next;
	}
	return { rows: rows.slice(0, maxRows), ok: true };
}
