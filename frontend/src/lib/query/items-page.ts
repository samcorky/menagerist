import { listNodes, type NodeResponse } from '$lib/api/client';
import { networkAwareError } from '$lib/api/errors';
import { decodeQuery, encodeQuery } from './codec';
import { fitsLimits } from './limits';
import { runSearch, SearchError, type SearchWarning } from './search';
import { combine, countConditions, emptyQuery, pageConditions, searchTextTooLong } from './tree';
import type { Path, Query } from './types';

/** The URL parameter that carries the filter. */
export const FILTER_PARAM = 'f';
export const ITEMS_PAGE_SIZE = 50;

export const INVALID_LINK_MESSAGE = "That filter link isn't valid.";
export const TOO_MANY_MESSAGE = 'Too many conditions to add the page filters. Remove a condition.';

/** The filter in the URL; `invalid` when a token is present but cannot be read. */
export function readFilter(token: string | null): { query: Query; invalid: boolean } {
	if (!token) return { query: emptyQuery(), invalid: false };
	const query = decodeQuery(token);
	return query ? { query, invalid: false } : { query: emptyQuery(), invalid: true };
}

/** The URL token for a filter, or null when there is nothing to carry. */
export function filterToken(query: Query): string | null {
	return countConditions(query) === 0 && query.sort.length === 0
		? null
		: encodeQuery({ ...query, where: countConditions(query) === 0 ? null : query.where });
}

/** Search params with the filter set or removed; other parameters are kept. */
export function withFilter(params: URLSearchParams, query: Query): URLSearchParams {
	const next = new URLSearchParams(params);
	const token = filterToken(query);
	if (token) next.set(FILTER_PARAM, token);
	else next.delete(FILTER_PARAM);
	return next;
}

/**
 * Whether the list needs the search endpoint. With no conditions and no sort the page keeps
 * using `GET /node`, so people who never open Filters see exactly what they did before.
 */
export function usesSearch(query: Query): boolean {
	return countConditions(query) > 0 || query.sort.length > 0;
}

const NUMBER = new Intl.NumberFormat('en-GB');

/** "12", or "1,000+" when the server stopped counting. */
export function formatCount(total: number, capped: boolean): string {
	return `${NUMBER.format(total)}${capped ? '+' : ''}`;
}

/** "12 items", "1 item", or "1,000+ items" when the server stopped counting. */
export function formatTotal(total: number, capped: boolean): string {
	const count = formatCount(total, capped);
	return `${count} ${total === 1 && !capped ? 'item' : 'items'}`;
}

/**
 * The count line, or null to hide it: hidden with no count, with no results (the empty state
 * says so), and during a fresh load, but kept while a further page is appended.
 */
export function totalLine(
	total: number | null,
	capped: boolean,
	state: { loading: boolean; appending: boolean }
): string | null {
	if (total === null || total === 0) return null;
	if (state.loading && !state.appending) return null;
	return formatTotal(total, capped);
}

export type PageBasics = { type: string | null; q: string };

/** Where the filter sits inside `combine(filter, basics)`, for mapping server paths back. */
export function combinePrefix(filter: Query, basics: PageBasics): Path {
	const extra = pageConditions(basics).length > 0;
	return extra && filter.where && filter.where.op !== 'and' ? [0] : [];
}

export const SEARCH_TOO_LONG_MESSAGE =
	'Search text is too long to use with filters, so it is not applied. Shorten it to 200 characters.';

/** Whether the page should say its search text was left out of a filtered search. */
export function searchTextIgnored(filter: Query, q: string): boolean {
	return usesSearch(filter) && searchTextTooLong(q);
}

export type ItemsPage =
	| {
			status: 'ok';
			items: NodeResponse[];
			hasMore: boolean;
			/** Search cursor for the next page; null on the list path. */
			cursor: string | null;
			/** Null on the list path, which does not count. */
			total: number | null;
			totalCapped: boolean;
			warnings: SearchWarning[];
			prefix: Path;
	  }
	| { status: 'too-many' }
	| { status: 'rejected'; detail: string }
	| { status: 'failed'; title: string; description?: string };

/**
 * Load one page of items. Without filter conditions this is the existing `GET /node` call
 * (paged by `after`); otherwise the page's type and search box are folded into the filter
 * and sent to `POST /node/search` (paged by cursor).
 */
export async function loadItemsPage(args: {
	filter: Query;
	basics: PageBasics;
	after?: string;
	cursor?: string | null;
	limit?: number;
}): Promise<ItemsPage> {
	const limit = args.limit ?? ITEMS_PAGE_SIZE;
	const { type, q } = args.basics;
	if (!usesSearch(args.filter)) {
		const result = await listNodes({
			query: { after: args.after, limit, type: type ?? undefined, q: q || undefined }
		});
		if (result.error || !result.data) return { status: 'failed', ...networkAwareError(result) };
		return {
			status: 'ok',
			items: result.data,
			hasMore: /rel="next"/.test(result.response?.headers.get('link') ?? ''),
			cursor: null,
			total: null,
			totalCapped: false,
			warnings: [],
			prefix: []
		};
	}
	const query = combine(args.filter, { type, q });
	if (!fitsLimits(query)) return { status: 'too-many' };
	try {
		const page = await runSearch({ query, limit, cursor: args.cursor ?? null });
		return {
			status: 'ok',
			items: page.items,
			hasMore: page.nextCursor !== null,
			cursor: page.nextCursor,
			total: page.total,
			totalCapped: page.totalCapped,
			warnings: page.warnings,
			prefix: combinePrefix(args.filter, args.basics)
		};
	} catch (e) {
		if (e instanceof SearchError && e.detail !== null && (e.status === 400 || e.status === 422))
			return { status: 'rejected', detail: e.detail };
		if (e instanceof SearchError)
			return { status: 'failed', title: e.title, description: e.description };
		return { status: 'failed', title: 'Something went wrong' };
	}
}

/**
 * Writes filter changes to the URL. Text-like edits wait `delay` ms so typing does not
 * navigate per key; any other change goes at once (and flushes a pending one). The first
 * write after `startSession` adds a history entry; later ones replace it, so Back leaves
 * the whole editing session in one step.
 */
export function createFilterWriter(
	navigate: (query: Query, replace: boolean) => void,
	delay = 250
): {
	write(query: Query, options?: { debounce?: boolean }): void;
	flush(): void;
	startSession(): void;
	cancel(): void;
} {
	let timer: ReturnType<typeof setTimeout> | null = null;
	let pending: Query | null = null;
	let pushed = false;
	const send = () => {
		if (timer !== null) clearTimeout(timer);
		timer = null;
		if (!pending) return;
		const query = pending;
		pending = null;
		navigate(query, pushed);
		pushed = true;
	};
	return {
		write(query, options) {
			pending = query;
			if (!options?.debounce) return send();
			if (timer !== null) clearTimeout(timer);
			timer = setTimeout(send, delay);
		},
		flush: send,
		startSession() {
			send();
			pushed = false;
		},
		cancel() {
			if (timer !== null) clearTimeout(timer);
			timer = null;
			pending = null;
		}
	};
}
