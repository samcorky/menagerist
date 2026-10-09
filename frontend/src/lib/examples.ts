import { listExampleEntities } from '$lib/api/client';
import type {
	InstallResultResponse,
	KeptEntityResponse,
	PackCountsResponse,
	UninstallResultResponse
} from '$lib/api/client';

const COUNT_PARTS: [keyof PackCountsResponse, string, string][] = [
	['item_types', 'item type', 'item types'],
	['items', 'item', 'items'],
	['collections', 'collection', 'collections'],
	['connections', 'connection', 'connections'],
	['relationship_types', 'connection type', 'connection types'],
	['presets', 'preset', 'presets']
];

function plural(n: number, one: string, many: string): string {
	return `${n} ${n === 1 ? one : many}`;
}

/** "3 item types, 14 items": the non-zero parts of a pack, in a fixed order. */
export function describeCounts(counts: PackCountsResponse): string {
	return COUNT_PARTS.filter(([key]) => counts[key] > 0)
		.map(([key, one, many]) => plural(counts[key], one, many))
		.join(', ');
}

const REASON_LABELS: Record<string, string> = {
	edited: 'you edited them',
	'has your connections, files or collections': 'they have your connections, files or collections',
	// Recorded by installs made before collections counted as your own data.
	'has your connections or files': 'they have your connections or files',
	'still in use': 'they are still in use'
};

/** A friendly phrase for why something was kept; unknown reasons stay neutral. */
export function reasonLabel(reason: string): string {
	return REASON_LABELS[reason] ?? 'they are no longer just examples';
}

/** Kept entries grouped by reason, in first-seen order. */
export function groupKept(kept: KeptEntityResponse[]): { reason: string; count: number }[] {
	const groups = new Map<string, number>();
	for (const entry of kept) groups.set(entry.reason, (groups.get(entry.reason) ?? 0) + 1);
	return [...groups].map(([reason, count]) => ({ reason, count }));
}

/** The toast text after removal: what went, then what stayed and why. */
export function describeRemoval(report: UninstallResultResponse): string {
	const removed = describeCounts(report.removed);
	const first = removed ? `Removed ${removed}.` : 'Nothing needed removing.';
	if (report.kept.length === 0) return first;
	const kept = groupKept(report.kept)
		.map(
			({ reason, count }) =>
				`${plural(count, 'item was', 'items were')} kept because ${reasonLabel(reason)}`
		)
		.join('; ');
	return `${first} ${kept}.`;
}

/** The toast text after an install, mentioning anything you'd kept that was taken back in. */
export function describeInstall(result: InstallResultResponse): string {
	const adopted = describeCounts(result.adopted);
	if (!adopted) return 'Examples added';
	const total = Object.values(result.adopted).reduce((sum, n) => sum + n, 0);
	return `Examples added. ${adopted} you'd kept ${total === 1 ? 'was' : 'were'} already here.`;
}

const BANNER_KEY = 'menagerist.examples.bannerDismissed';

/** Whether the "you have examples" line was dismissed; a private window may refuse storage. */
export function isExamplesBannerDismissed(): boolean {
	try {
		return localStorage.getItem(BANNER_KEY) === 'true';
	} catch {
		return false;
	}
}

export function dismissExamplesBanner(): void {
	try {
		localStorage.setItem(BANNER_KEY, 'true');
	} catch {
		// Storage unavailable: the line returns on the next visit.
	}
}

const FILTER_KEY = 'menagerist.examples.filter';
const LEGACY_HIDE_KEY = 'menagerist.examples.hide';

export type ExampleFilter = 'all' | 'hide' | 'only';

export const EXAMPLE_FILTER_LABELS: Record<ExampleFilter, string> = {
	all: 'All items',
	hide: 'Hide examples',
	only: 'Only examples'
};

/** Which items the list shows; defaults to all. Reads the older hide-only flag too. */
export function readExampleFilter(): ExampleFilter {
	try {
		const saved = localStorage.getItem(FILTER_KEY);
		if (saved === 'hide' || saved === 'only') return saved;
		if (saved === null && localStorage.getItem(LEGACY_HIDE_KEY) === 'true') return 'hide';
		return 'all';
	} catch {
		return 'all';
	}
}

export function writeExampleFilter(filter: ExampleFilter): void {
	try {
		localStorage.setItem(FILTER_KEY, filter);
	} catch {
		// Storage unavailable: the choice applies to this page only.
	}
}

export interface ExampleIds {
	items: ReadonlySet<string>;
	itemTypes: ReadonlySet<string>;
	collections: ReadonlySet<string>;
}

const NO_EXAMPLES: ExampleIds = {
	items: new Set(),
	itemTypes: new Set(),
	collections: new Set()
};
let cached: Promise<ExampleIds> | null = null;

/** Ids owned by an installed example pack; empty if the lookup fails. Cached until invalidated. */
export function loadExampleIds(): Promise<ExampleIds> {
	cached ??= listExampleEntities()
		.then((result) =>
			result.data
				? {
						items: new Set(result.data.item_ids),
						itemTypes: new Set(result.data.item_type_ids),
						collections: new Set(result.data.collection_ids)
					}
				: NO_EXAMPLES
		)
		.catch(() => NO_EXAMPLES);
	return cached;
}

/** Forget the cached ids; call after an install or removal. */
export function invalidateExampleIds(): void {
	cached = null;
}

/** Keep all items, only the non-examples, or only the examples. */
export function visibleItems<T extends { id: string }>(
	items: T[],
	exampleIds: ReadonlySet<string>,
	filter: ExampleFilter
): T[] {
	if (filter === 'all') return items;
	return items.filter((item) => exampleIds.has(item.id) === (filter === 'only'));
}
