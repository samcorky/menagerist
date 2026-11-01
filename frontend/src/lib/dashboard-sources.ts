import {
	countNodeSearches,
	countNodeTypes,
	type CollectionResponse,
	type NodeResponse,
	type NodeTypeResponse
} from '$lib/api/client';
import { fetchAllCollections } from '$lib/collections';
import {
	editedQuery,
	everythingQuery,
	favouriteQuery,
	monthQuery,
	newestQuery,
	photoQuery,
	type TidyRow
} from '$lib/dashboard';
import { runSearch } from '$lib/query/search';
import type { Query } from '$lib/query/types';

// Each Home block loads on its own, so one slow or failed block never holds the others back.
export type Block<T> = { status: 'ok'; data: T } | { status: 'error' };

/** A match count; `capped` only past the server's ceiling (100,000), otherwise it is exact. */
export type Count = { total: number; capped: boolean };

export const NEWEST_LIMIT = 8;
export const EDITED_LIMIT = 5;

async function guarded<T>(load: () => Promise<T>): Promise<Block<T>> {
	try {
		return { status: 'ok', data: await load() };
	} catch {
		return { status: 'error' };
	}
}

/**
 * How many items each named query matches, in one request. The server parses the queries the
 * way a search does, so a count always agrees with the list the same filter opens.
 */
async function countSearches(queries: Record<string, Query>): Promise<Record<string, Count>> {
	const result = await countNodeSearches({ body: { queries } });
	if (result.error || !result.data) throw new Error('count failed');
	return Object.fromEntries(
		Object.entries(result.data.counts).map(([name, count]) => [
			name,
			{ total: count.total, capped: count.total_capped }
		])
	);
}

export const loadNewest = (): Promise<Block<NodeResponse[]>> =>
	guarded(async () => (await runSearch({ query: newestQuery(), limit: NEWEST_LIMIT })).items);

export const loadEdited = (): Promise<Block<NodeResponse[]>> =>
	guarded(async () => (await runSearch({ query: editedQuery(), limit: EDITED_LIMIT })).items);

/** Every collection (a smart collection's count is capped at 1,000 by the server). */
export const loadCollections = (): Promise<Block<CollectionResponse[]>> =>
	guarded(async () => {
		const all = await fetchAllCollections();
		if (all === null) throw new Error('collections failed');
		return all;
	});

export type Stats = {
	items: number;
	favourites: number;
	month: Count;
	withPhoto: Count;
};

export const loadStats = (): Promise<Block<Stats>> =>
	guarded(async () => {
		const counts = await countSearches({
			items: everythingQuery(),
			favourites: favouriteQuery(),
			month: monthQuery(),
			photo: photoQuery()
		});
		const need = (name: string): Count => {
			if (!counts[name]) throw new Error(`no count for ${name}`);
			return counts[name];
		};
		return {
			items: need('items').total,
			favourites: need('favourites').total,
			month: need('month'),
			withPhoto: need('photo')
		};
	});

export type TypeBreakdown = {
	/** Only item types that have at least one of your items; the instance's list is shared. */
	rows: { slug: string; label: string; count: number }[];
	/** Items with no item type. */
	untyped: number;
};

/** Items per item type in use, biggest first, as the server counts them. */
export const loadTypeBreakdown = (types: NodeTypeResponse[]): Promise<Block<TypeBreakdown>> =>
	guarded(async () => {
		const result = await countNodeTypes();
		if (result.error || !result.data) throw new Error('count failed');
		const labels = new Map(types.map((type) => [type.slug, type.label]));
		const rows: TypeBreakdown['rows'] = [];
		let untyped = 0;
		for (const row of result.data) {
			if (row.type === null) untyped = row.count;
			else rows.push({ slug: row.type, label: labels.get(row.type) ?? row.type, count: row.count });
		}
		return { rows, untyped };
	});

export type TidyResult = { row: TidyRow; count: Count | null };

/** A count per row; if the request fails the rows stay, with no number. */
export async function loadTidy(rows: TidyRow[]): Promise<TidyResult[]> {
	if (rows.length === 0) return [];
	let counts: Record<string, Count> = {};
	try {
		counts = await countSearches(Object.fromEntries(rows.map((row) => [row.id, row.query])));
	} catch {
		// Leave every count empty.
	}
	return rows.map((row) => ({ row, count: counts[row.id] ?? null }));
}
