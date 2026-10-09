import {
	listCollections,
	listNodes,
	listNodeTypes,
	type CollectionResponse,
	type NodeResponse,
	type NodeTypeResponse
} from '$lib/api/client';
import {
	GROUP_CAPS,
	type PalettePage,
	matchItemTypes,
	matchPages,
	rankByName
} from '$lib/palette-search';
import { normaliseQuery } from '$lib/search-palette';

export type GroupKey = 'items' | 'collections' | 'itemTypes' | 'pages';
export type AsyncGroupKey = 'items' | 'collections' | 'itemTypes';
export type GroupState<T> = { status: 'ok'; rows: T[] } | { status: 'error' };
export type Results = {
	items: GroupState<NodeResponse>;
	collections: GroupState<CollectionResponse>;
	itemTypes: GroupState<NodeTypeResponse>;
	pages: PalettePage[];
};

const ITEM_TYPE_PAGE = 100;
export const ITEM_TYPE_CAP = 1000;

let typesPromise: Promise<NodeTypeResponse[]> | null = null;

/** Clears the cached item type list (tests). */
export function resetItemTypeCache(): void {
	typesPromise = null;
}

/** Pages through every item type by cursor, stopping at a short page or {@link ITEM_TYPE_CAP}. */
async function fetchItemTypes(): Promise<NodeTypeResponse[]> {
	const all: NodeTypeResponse[] = [];
	let after: string | undefined;
	while (all.length < ITEM_TYPE_CAP) {
		const limit = Math.min(ITEM_TYPE_PAGE, ITEM_TYPE_CAP - all.length);
		const result = await listNodeTypes({ query: after ? { limit, after } : { limit } });
		if (result.error || !result.data) throw new Error('item types unavailable');
		all.push(...result.data);
		if (result.data.length < limit) break;
		after = result.data[result.data.length - 1].id;
	}
	return all;
}

// Loaded once (also used for item row labels); a failed load is dropped so the next search retries.
export function loadItemTypes(): Promise<NodeTypeResponse[]> {
	if (!typesPromise) {
		const attempt = fetchItemTypes();
		typesPromise = attempt;
		attempt.catch(() => {
			if (typesPromise === attempt) typesPromise = null;
		});
	}
	return typesPromise;
}

/** Searches every source for the query, reporting each group as it settles. `only` re-runs just those async sources. */
export async function searchEverything(
	query: string,
	onUpdate: (partial: Partial<Results>) => void,
	isCurrent: () => boolean,
	only?: AsyncGroupKey[]
): Promise<void> {
	const q = normaliseQuery(query);
	const emit = (partial: Partial<Results>) => {
		if (isCurrent()) onUpdate(partial);
	};

	if (!q) {
		emit({
			items: { status: 'ok', rows: [] },
			collections: { status: 'ok', rows: [] },
			itemTypes: { status: 'ok', rows: [] },
			pages: []
		});
		return;
	}

	if (!only) emit({ pages: matchPages(q) });
	const wanted = (key: AsyncGroupKey) => !only || only.includes(key);

	const settle = async <T>(key: AsyncGroupKey, load: () => Promise<T[]>): Promise<void> => {
		if (!wanted(key)) return;
		let state: GroupState<T>;
		try {
			state = { status: 'ok', rows: await load() };
		} catch {
			state = { status: 'error' };
		}
		emit({ [key]: state });
	};

	await Promise.all([
		settle('items', async () => {
			const result = await listNodes({ query: { q, limit: GROUP_CAPS.items } });
			if (result.error || !result.data) throw new Error('items unavailable');
			return rankByName(result.data, q, (row) => row.name).slice(0, GROUP_CAPS.items);
		}),
		settle('collections', async () => {
			const result = await listCollections({ query: { q, limit: GROUP_CAPS.collections } });
			if (result.error || !result.data) throw new Error('collections unavailable');
			return rankByName(result.data, q, (row) => row.name).slice(0, GROUP_CAPS.collections);
		}),
		settle('itemTypes', async () => matchItemTypes(await loadItemTypes(), q))
	]);
}
