import {
	listCollections,
	listInstanceSettings,
	listJobs,
	listNodes,
	listNodeTypes,
	type CollectionResponse,
	type JobResponse,
	type SettingResponse,
	type NodeResponse,
	type NodeTypeResponse
} from '$lib/api/client';
import {
	GROUP_CAPS,
	type PaletteLayout,
	type PalettePage,
	matchItemTypes,
	matchPages,
	matchSettings,
	matchTasks,
	rankByName
} from '$lib/palette-search';
import { normaliseQuery } from '$lib/search-palette';

export type GroupKey =
	'items' | 'collections' | 'itemTypes' | 'pages' | 'settings' | 'tasks' | 'collectionItems';
export type AsyncGroupKey = Exclude<GroupKey, 'pages'>;
export type GroupState<T> = { status: 'ok'; rows: T[] } | { status: 'error' };
export type Results = {
	items: GroupState<NodeResponse>;
	collections: GroupState<CollectionResponse>;
	itemTypes: GroupState<NodeTypeResponse>;
	settings: GroupState<SettingResponse>;
	tasks: GroupState<JobResponse>;
	collectionItems: GroupState<NodeResponse>;
	pages: PalettePage[];
};

/** What the person may open and where they are, from which the groups searched follow. */
export type SearchScope = {
	layout: PaletteLayout;
	canSettings: boolean;
	canTasks: boolean;
};

export const DEFAULT_SCOPE: SearchScope = {
	layout: {
		order: [],
		collection: null,
		caps: { ...GROUP_CAPS }
	},
	canSettings: false,
	canTasks: false
};

const ITEM_TYPE_PAGE = 100;
export const ITEM_TYPE_CAP = 1000;

let typesPromise: Promise<NodeTypeResponse[]> | null = null;
let settingsPromise: Promise<SettingResponse[]> | null = null;
let tasksPromise: Promise<JobResponse[]> | null = null;

/** Clears the cached lists (tests). */
export function resetItemTypeCache(): void {
	typesPromise = null;
	settingsPromise = null;
	tasksPromise = null;
}

// Cached once like the item types; a failed load is dropped so the next search retries.
function cached<T>(
	current: Promise<T> | null,
	set: (p: Promise<T> | null) => void,
	load: () => Promise<T>
) {
	if (current) return current;
	const attempt = load();
	set(attempt);
	attempt.catch(() => set(null));
	return attempt;
}

function loadSettings(): Promise<SettingResponse[]> {
	return cached(
		settingsPromise,
		(p) => (settingsPromise = p),
		async () => {
			const result = await listInstanceSettings();
			if (result.error || !result.data) throw new Error('settings unavailable');
			return result.data;
		}
	);
}

function loadTasks(): Promise<JobResponse[]> {
	return cached(
		tasksPromise,
		(p) => (tasksPromise = p),
		async () => {
			const result = await listJobs();
			if (result.error || !result.data) throw new Error('tasks unavailable');
			return result.data;
		}
	);
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

/** Search every source and report each group as it settles. */
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
		emit({
			items: { status: 'ok', rows: [] },
			collections: { status: 'ok', rows: [] },
			itemTypes: { status: 'ok', rows: [] },
			settings: { status: 'ok', rows: [] },
			tasks: { status: 'ok', rows: [] },
			collectionItems: { status: 'ok', rows: [] },
			pages: []
		});
		return;
	}

	if (!only) emit({ pages: matchPages(q) });
	const wanted = (key: AsyncGroupKey) => !only || only.includes(key);
	const { caps, collection } = scope.layout;

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

	// A group the person may not open, or that has no context here, is simply empty.
	const none = async (): Promise<never[]> => [];

	await Promise.all([
		settle('items', async () => {
			const result = await listNodes({ query: { q, limit: caps.items } });
			if (result.error || !result.data) throw new Error('items unavailable');
			return rankByName(result.data, q, (row) => row.name).slice(0, caps.items);
		}),
		settle('collectionItems', async () => {
			if (!collection) return none();
			const result = await listNodes({ query: { q, collection, limit: caps.collectionItems } });
			if (result.error || !result.data) throw new Error('items unavailable');
			return rankByName(result.data, q, (row) => row.name).slice(0, caps.collectionItems);
		}),
		settle('collections', async () => {
			const result = await listCollections({ query: { q, limit: caps.collections } });
			if (result.error || !result.data) throw new Error('collections unavailable');
			return rankByName(result.data, q, (row) => row.name).slice(0, caps.collections);
		}),
		settle('itemTypes', async () => matchItemTypes(await loadItemTypes(), q, caps.itemTypes)),
		settle('settings', async () =>
			scope.canSettings ? matchSettings(await loadSettings(), q, caps.settings) : none()
		),
		settle('tasks', async () =>
			scope.canTasks ? matchTasks(await loadTasks(), q, caps.tasks) : none()
		)
	]);
}
