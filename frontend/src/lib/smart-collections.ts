import {
	createCollection,
	updateCollection,
	type CollectionResponse,
	type NodeResponse
} from '$lib/api/client';
import { errorMessage } from '$lib/api/errors';
import { chipModels, type Chip } from '$lib/query/builder';
import { parseQuery } from '$lib/query/codec';
import { formatCount } from '$lib/query/items-page';
import type { SummaryLookup } from '$lib/query/summary';
import { runSearch, type SearchWarning } from '$lib/query/search';
import type { Query } from '$lib/query/types';
import { mapWarnings, parseQueryPath, type QueryTarget } from '$lib/query/warnings';

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

const FALLBACK_MESSAGE = "Couldn't save the smart collection. Try again.";

function failure(result: { error?: unknown; response?: Response | null }): SmartCollectionError {
	const status = result.response?.status ?? null;
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
	warnings: SearchWarning[];
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
	opts: { cursor?: string | null; limit?: number }
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
			warnings: mergeWarnings(own)
		};
	}
	const page = await runSearch({ query, limit: opts.limit, cursor: opts.cursor });
	return {
		query,
		items: page.items,
		total: page.total,
		totalCapped: page.totalCapped,
		nextCursor: page.nextCursor,
		warnings: mergeWarnings(own, page.warnings)
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
