import {
	countCollectionItems,
	createCollection,
	updateCollection,
	type CollectionResponse,
	type NodeResponse
} from '$lib/api/client';
import { errorMessage } from '$lib/api/errors';
import { chipModels, conditionNumbers, type Chip } from '$lib/query/builder';
import { parseQuery } from '$lib/query/codec';
import { formatCount } from '$lib/query/items-page';
import { fitsLimits } from '$lib/query/limits';
import { combineWithSaved, needsNarrowing, type NarrowBasics } from '$lib/query/narrow';
import type { SummaryLookup } from '$lib/query/summary';
import { runSearch, type SearchWarning } from '$lib/query/search';
import type { Query } from '$lib/query/types';
import { describeItemCount } from '$lib/collections';
import { mapWarnings, parseQueryPath, pathKey, type QueryTarget } from '$lib/query/warnings';

/** Shown in place of the conditions when a saved definition cannot be read. */
export const UNREADABLE_CONDITIONS_MESSAGE = "These conditions can't be shown";

/** A smart collection (one with a saved search), as opposed to a manual one. */
export function isSmart(collection: Pick<CollectionResponse, 'kind'>): boolean {
	return collection.kind === 'dynamic';
}

/** "12", or "1,000+" when the count was capped. */
export function countLabel(count: number, capped: boolean): string {
	return formatCount(count, capped);
}

/** Defence in depth: the server is asked for `kind=manual`, but smart collections fill themselves and never take items by hand. */
export function manualCollections<T extends Pick<CollectionResponse, 'kind'>>(
	collections: readonly T[]
): T[] {
	return collections.filter((c) => !isSmart(c));
}

/** "No items", "1 item", "12 items", or "1,000+ items" for a capped smart collection. */
export function describeCollectionCount(
	collection: Pick<CollectionResponse, 'kind' | 'item_count' | 'item_count_capped'>
): string {
	if (!isSmart(collection)) return describeItemCount(collection.item_count);
	const capped = collection.item_count_capped ?? false;
	if (!capped && collection.item_count <= 1) return describeItemCount(collection.item_count);
	return `${countLabel(collection.item_count, capped)} items`;
}

/**
 * A failed create or update. `path` and `target` say which condition or sort key the
 * server rejected (400 only); `status` is null when there was no response.
 */
export class SmartCollectionError extends Error {
	readonly status: number | null;
	readonly path: string | null;
	readonly target: QueryTarget | null;

	constructor(
		status: number | null,
		message: string,
		path: string | null = null,
		target: QueryTarget | null = null
	) {
		super(message);
		this.name = 'SmartCollectionError';
		this.status = status;
		this.path = path;
		this.target = target;
	}
}

/** The error text for a save, naming the condition ("Condition 2: ...") when the server did. */
export function describeSaveError(error: SmartCollectionError, query: Query): string {
	const where = error.target && 'where' in error.target ? error.target.where : null;
	const n = where ? conditionNumbers(query).get(pathKey(where)) : undefined;
	return n ? `Condition ${n}: ${error.message}` : error.message;
}

const FALLBACK_MESSAGE = "Couldn't save the smart collection. Try again.";

export const CHANGED_ELSEWHERE_MESSAGE =
	'This collection was changed elsewhere. Reload to see the latest conditions.';

/** Shown for a smart collection that has no conditions. */
export const MATCHES_EVERY_ITEM_MESSAGE = 'Matches every item';

function failure(result: { error?: unknown; response?: Response | null }): SmartCollectionError {
	const status = result.response?.status ?? null;
	if (status === 412) return new SmartCollectionError(status, CHANGED_ELSEWHERE_MESSAGE);
	if (status === 400 || status === 409 || status === 422) {
		const detail = errorMessage(result.error);
		const match = /^([a-z_.[\]0-9]+): (.+)$/s.exec(detail);
		const target = match ? parseQueryPath(match[1]) : null;
		if (match && target) return new SmartCollectionError(status, match[2], match[1], target);
		return new SmartCollectionError(status, detail);
	}
	return new SmartCollectionError(status, FALLBACK_MESSAGE);
}

async function send(
	call: () => Promise<{ data?: CollectionResponse; error?: unknown; response?: Response | null }>
): Promise<CollectionResponse> {
	let result: Awaited<ReturnType<typeof call>>;
	try {
		result = await call();
	} catch {
		throw new SmartCollectionError(null, FALLBACK_MESSAGE);
	}
	if (result.error || !result.data) throw failure(result);
	return result.data;
}

/** Create a smart collection from a search. Rejects with a SmartCollectionError. */
export function saveSmartCollection(name: string, query: Query): Promise<CollectionResponse> {
	return send(() =>
		createCollection({
			body: { name: name.trim(), definition: query as unknown as Record<string, unknown> }
		})
	);
}

/** Replace a smart collection's conditions. Rejects with a SmartCollectionError. */
export function updateDefinition(id: string, query: Query): Promise<CollectionResponse> {
	return send(() =>
		updateCollection({
			path: { collection_id: id },
			body: { definition: query as unknown as Record<string, unknown> }
		})
	);
}

export type SmartCollectionPage = {
	/** The decoded saved query; null when the definition cannot be read. */
	query: Query | null;
	items: NodeResponse[];
	total: number;
	totalCapped: boolean;
	nextCursor: string | null;
	/** The collection's own warnings merged with the search's. */
	warnings: SearchWarning[];
	/** Only what the search reported (paths in the tree that was sent). */
	searchWarnings: SearchWarning[];
	/** The saved and ad-hoc conditions together exceed the limits, so nothing was searched. */
	tooLarge: boolean;
};

function mergeWarnings(...lists: SearchWarning[][]): SearchWarning[] {
	const seen = new Set<string>();
	const merged: SearchWarning[] = [];
	for (const { path, message } of lists.flat()) {
		const key = `${path}\u0000${message}`;
		if (seen.has(key)) continue;
		seen.add(key);
		merged.push({ path, message });
	}
	return merged;
}

/**
 * Run a smart collection's saved search (with its saved sort) for the viewer. A definition the
 * decoder rejects gives `query: null` and no items, never an error. Search failures reject
 * with a SearchError.
 */
export async function loadSmartCollection(
	collection: Pick<CollectionResponse, 'definition' | 'warnings'>,
	opts: {
		cursor?: string | null;
		limit?: number;
		/** The page's own filters, ANDed onto the saved conditions (never saved by this). */
		narrow?: { adhoc: Query; basics: NarrowBasics };
	}
): Promise<SmartCollectionPage> {
	const own = collection.warnings ?? [];
	const query = parseQuery(collection.definition);
	if (!query) {
		return {
			query: null,
			items: [],
			total: 0,
			totalCapped: false,
			nextCursor: null,
			warnings: mergeWarnings(own),
			searchWarnings: [],
			tooLarge: false
		};
	}
	const { narrow } = opts;
	const sent =
		narrow && needsNarrowing(narrow.adhoc, narrow.basics)
			? combineWithSaved(query, narrow.adhoc, narrow.basics)
			: query;
	if (!fitsLimits(sent)) {
		return {
			query,
			items: [],
			total: 0,
			totalCapped: false,
			nextCursor: null,
			warnings: mergeWarnings(own),
			searchWarnings: [],
			tooLarge: true
		};
	}
	const page = await runSearch({ query: sent, limit: opts.limit, cursor: opts.cursor });
	return {
		query,
		items: page.items,
		total: page.total,
		totalCapped: page.totalCapped,
		nextCursor: page.nextCursor,
		warnings: mergeWarnings(own, page.warnings),
		searchWarnings: page.warnings,
		tooLarge: false
	};
}

/**
 * The conditions as chips, the same texts the filter builder shows; null when the definition
 * cannot be read (show UNREADABLE_CONDITIONS_MESSAGE).
 */
export function smartCollectionSummary(
	definition: unknown,
	lookup: SummaryLookup,
	warnings: SearchWarning[] = []
): { lead: string | null; chips: Chip[] } | null {
	const query = parseQuery(definition);
	if (!query) return null;
	return chipModels(query, lookup, mapWarnings(warnings).conditions);
}

export const EXACT_COUNT_ERROR = "Couldn't count the items. Try again.";

/** A failed exact count. `status` is null when there was no response. */
export class ExactCountError extends Error {
	readonly status: number | null;

	constructor(status: number | null) {
		super(EXACT_COUNT_ERROR);
		this.name = 'ExactCountError';
		this.status = status;
	}
}

/** The uncapped number of items in a collection. Rejects with an ExactCountError. */
export async function fetchExactCount(collectionId: string, signal?: AbortSignal): Promise<number> {
	let result: Awaited<ReturnType<typeof countCollectionItems>>;
	try {
		result = await countCollectionItems({
			path: { collection_id: collectionId },
			signal
		});
	} catch {
		throw new ExactCountError(null);
	}
	if (result.error || !result.data) throw new ExactCountError(result.response?.status ?? null);
	return result.data.count;
}
