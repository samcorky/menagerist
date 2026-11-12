import {
	listNodes,
	listNodeTypes,
	searchEverything as searchApi,
	type NodeResponse,
	type NodeTypeResponse,
	type SearchHitResponse,
	type SearchKind
} from '$lib/api/client';
import {
	GROUP_CAPS,
	type PaletteGroup,
	type PaletteLayout,
	type PalettePage,
	matchPages,
	rankByName
} from '$lib/palette-search';
import { normaliseQuery } from '$lib/search-palette';

export type GroupKey = PaletteGroup;
export type AsyncGroupKey = Exclude<GroupKey, 'pages'>;
export type GroupState<T> = { status: 'ok'; rows: T[] } | { status: 'error' };
/** One row of any searched group: the server's hit, or an item of the collection in view. */
export type Hit = SearchHitResponse;
export type Results = Record<AsyncGroupKey, GroupState<Hit>> & { pages: PalettePage[] };

/** Where the person is, which decides the extra collection search and how many rows each group gets. */
export type SearchScope = { layout: PaletteLayout };

export const DEFAULT_SCOPE: SearchScope = {
	layout: { order: [], collection: null, caps: { ...GROUP_CAPS } }
};

// The kind the server reports for each group it answers.
const KIND_GROUP: Record<SearchKind, AsyncGroupKey> = {
	item: 'items',
	collection: 'collections',
	item_type: 'itemTypes',
	setting: 'settings',
	scheduled_task: 'tasks'
};
const SERVER_GROUPS = Object.values(KIND_GROUP);
const MAX_LIMIT = 50;

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

/** An item of the collection in view, shaped like the server's hits. */
function itemHit(node: NodeResponse): Hit {
	return {
		kind: 'item',
		ref: node.id,
		title: node.name,
		description: node.description ?? null,
		group: node.type ?? null,
		attributes: node.attributes ?? null,
		score: 0
	};
}

const emptyGroups = (): Omit<Results, 'pages'> => ({
	items: { status: 'ok', rows: [] },
	collections: { status: 'ok', rows: [] },
	itemTypes: { status: 'ok', rows: [] },
	settings: { status: 'ok', rows: [] },
	tasks: { status: 'ok', rows: [] },
	collectionItems: { status: 'ok', rows: [] }
});

/** Search everything and report each group as it settles. */
export async function searchEverything(
	query: string,
	onUpdate: (partial: Partial<Results>) => void,
	isCurrent: () => boolean,
	only?: AsyncGroupKey[],
	scope: SearchScope = DEFAULT_SCOPE
): Promise<void> {
	const q = normaliseQuery(query);
	const emit = (partial: Partial<Results>) => {
		if (isCurrent()) onUpdate(partial);
	};

	if (!q) {
		emit({ ...emptyGroups(), pages: [] });
		return;
	}

	if (!only) emit({ pages: matchPages(q) });
	const wanted = (key: AsyncGroupKey) => !only || only.includes(key);
	const { caps, collection } = scope.layout;

	// One request answers every kind the server knows; a retry asks again for the same.
	const server = async (): Promise<void> => {
		const groups = SERVER_GROUPS.filter(wanted);
		if (groups.length === 0) return;
		const limit = Math.min(MAX_LIMIT, Math.max(...groups.map((key) => caps[key])));
		const failed = (keys: AsyncGroupKey[]) =>
			emit(Object.fromEntries(keys.map((key) => [key, { status: 'error' }])));
		try {
			const result = await searchApi({ query: { q, limit } });
			if (result.error || !result.data) return failed(groups);
			const down = new Set(result.data.failed.map((kind) => KIND_GROUP[kind]));
			const partial: Partial<Results> = {};
			for (const key of groups) {
				const rows = result.data.results
					.filter((hit) => KIND_GROUP[hit.kind] === key)
					.slice(0, caps[key]);
				partial[key as 'items'] = down.has(key) ? { status: 'error' } : { status: 'ok', rows };
			}
			emit(partial);
		} catch {
			failed(groups);
		}
	};

	// The collection in view is searched on its own: the server has no collection filter yet.
	const inCollection = async (): Promise<void> => {
		if (!wanted('collectionItems')) return;
		let state: GroupState<Hit>;
		try {
			if (!collection) {
				state = { status: 'ok', rows: [] };
			} else {
				const result = await listNodes({
					query: { q, collection, limit: caps.collectionItems }
				});
				if (result.error || !result.data) throw new Error('items unavailable');
				const rows = rankByName(result.data, q, (row) => row.name)
					.slice(0, caps.collectionItems)
					.map(itemHit);
				state = { status: 'ok', rows };
			}
		} catch {
			state = { status: 'error' };
		}
		emit({ collectionItems: state });
	};

	await Promise.all([server(), inCollection()]);
}
