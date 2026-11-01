import { searchNodes, type NodeResponse } from '$lib/api/client';
import { errorMessage, networkAwareError } from '$lib/api/errors';
import type { Query } from './types';

export const SEARCH_PAGE_SIZE = 50;

export type SearchWarning = { path: string; message: string };

export type SearchPage = {
	items: NodeResponse[];
	total: number;
	totalCapped: boolean;
	nextCursor: string | null;
	warnings: SearchWarning[];
};

/**
 * A failed search. `status` is null when there was no response (offline);
 * `detail` is the server's message for 4xx responses, otherwise null.
 * `title` and `description` are the generic user-facing text.
 */
export class SearchError extends Error {
	readonly status: number | null;
	readonly detail: string | null;
	readonly title: string;
	readonly description: string | undefined;

	constructor(result: { error?: unknown; response?: Response | null }) {
		const { title, description } = networkAwareError(result);
		super(title);
		this.name = 'SearchError';
		this.title = title;
		this.description = description;
		this.status = result.response?.status ?? null;
		this.detail = this.status !== null && this.status < 500 ? errorMessage(result.error) : null;
	}
}

export async function runSearch(args: {
	query: Query;
	limit?: number;
	cursor?: string | null;
}): Promise<SearchPage> {
	let result: Awaited<ReturnType<typeof searchNodes>>;
	try {
		result = await searchNodes({
			body: {
				query: args.query,
				limit: args.limit ?? SEARCH_PAGE_SIZE,
				cursor: args.cursor ?? null
			}
		});
	} catch {
		throw new SearchError({});
	}
	const { data } = result;
	if (result.error || !data) throw new SearchError(result);
	return {
		items: data.items,
		total: data.total,
		totalCapped: data.total_capped,
		nextCursor: data.next_cursor ?? null,
		warnings: data.warnings.map(({ path, message }) => ({ path, message }))
	};
}
