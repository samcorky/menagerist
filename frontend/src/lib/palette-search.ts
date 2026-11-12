import type { RouteId } from '$app/types';
import { foldText } from '$lib/fold-text';
import { settingId } from '$lib/settings-form';
import { jobId } from '$lib/scheduled-tasks';

export const GROUP_CAPS = {
	items: 5,
	collections: 3,
	itemTypes: 3,
	pages: 4,
	settings: 4,
	tasks: 3,
	collectionItems: 5
} as const;

/** Every group the popup can show. */
export type PaletteGroup = keyof typeof GROUP_CAPS;

/** Routes without parameters, so `resolve(path)` needs no params. */
export type StaticRoute = Exclude<RouteId, `${string}[${string}`>;
export type PalettePage = { label: string; path: StaticRoute };

export const PAGES: (PalettePage & { keywords: string[] })[] = [
	{ label: 'Home', path: '/', keywords: [] },
	{ label: 'Items', path: '/items', keywords: [] },
	{ label: 'Collections', path: '/collections', keywords: [] },
	{ label: 'Explore', path: '/explore', keywords: [] },
	{ label: 'Settings', path: '/settings', keywords: [] },
	{ label: 'Item types', path: '/settings/item-types', keywords: [] },
	{ label: 'Relationships', path: '/settings/relationships', keywords: ['connections'] },
	{ label: 'Saved fields', path: '/settings/saved-fields', keywords: [] },
	{ label: 'Examples', path: '/settings/examples', keywords: [] },
	{ label: 'Status', path: '/status', keywords: [] }
];

/** 0 exact, 1 name starts with, 2 a word in the name starts with, 3 anything else. */
export function matchRank(name: string, query: string): 0 | 1 | 2 | 3 {
	const n = foldText(name);
	const q = foldText(query.trim());
	if (n === q) return 0;
	if (n.startsWith(q)) return 1;
	if (n.split(/[^\p{L}\p{N}]+/u).some((word) => word.startsWith(q))) return 2;
	return 3;
}

/** Rows ordered by match rank; ties keep input order. */
export function rankByName<T>(rows: T[], query: string, nameOf: (row: T) => string): T[] {
	return rows
		.map((row, index) => ({ row, index, rank: matchRank(nameOf(row), query) }))
		.sort((a, b) => a.rank - b.rank || a.index - b.index)
		.map(({ row }) => row);
}

const contains = (text: string, needle: string) => foldText(text).includes(needle);

/** App pages whose label or keyword contains the query, best first. */
export function matchPages(query: string): PalettePage[] {
	const q = foldText(query.trim());
	if (!q) return [];
	const hits = PAGES.filter(
		(page) => contains(page.label, q) || page.keywords.some((k) => contains(k, q))
	);
	return rankByName(hits, q, (page) => page.label)
		.slice(0, GROUP_CAPS.pages)
		.map(({ label, path }) => ({ label, path }));
}

export type PaletteSetting = { key: string; group: string };
export type PaletteTask = { job_key: string };

/** Where a setting lives: its section of the admin settings page, scrolled to the setting. */
export function settingPath(
	setting: Pick<PaletteSetting, 'key' | 'group'>
): `/admin/settings?${string}#${string}` {
	const section = new URLSearchParams({ section: setting.group }).toString();
	return `/admin/settings?${section}#${settingId(setting.key)}`;
}

/** Where a scheduled task is on the scheduled tasks page, highlighted. */
export function taskPath(task: Pick<PaletteTask, 'job_key'>): `/admin/scheduled-tasks#${string}` {
	return `/admin/scheduled-tasks#${jobId(task.job_key)}`;
}

export type PaletteLayout = {
	/** Groups in display order. */
	order: PaletteGroup[];
	/** The collection whose items rank first, by the segment in the address; null elsewhere. */
	collection: string | null;
	/** Row cap per group; the first group gets room for a few more. */
	caps: Record<PaletteGroup, number>;
};

const DEFAULT_ORDER: PaletteGroup[] = [
	'items',
	'collections',
	'itemTypes',
	'pages',
	'settings',
	'tasks'
];
const LEAD_BONUS = 3;

/**
 * The group order and caps for the page the person is on: what they are looking at ranks first,
 * everything else is still searched. On a collection page that collection's items lead.
 */
export function paletteLayout(pathname: string): PaletteLayout {
	const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
	let lead: PaletteGroup[] = [];
	let collection: string | null = null;
	const inCollection = /^\/collections\/([^/]+)$/.exec(path);
	if (inCollection) {
		try {
			collection = decodeURIComponent(inCollection[1]);
		} catch {
			collection = inCollection[1];
		}
		lead = ['collectionItems'];
	} else if (path === '/collections') lead = ['collections'];
	else if (path === '/settings/item-types') lead = ['itemTypes'];
	else if (path === '/admin/scheduled-tasks') lead = ['tasks', 'settings'];
	else if (path === '/admin' || path.startsWith('/admin/')) lead = ['settings', 'tasks'];
	else if (path === '/items') lead = ['items'];

	const order = [...lead, ...DEFAULT_ORDER.filter((key) => !lead.includes(key))];
	const caps: Record<PaletteGroup, number> = { ...GROUP_CAPS };
	if (lead.length > 0) caps[order[0]] += LEAD_BONUS;
	return { order, collection, caps };
}

const SNIPPET_RADIUS = 40;

/**
 * Why a result matched when its title did not: a short stretch of the description around the
 * first hit, with ellipses where it is cut. Null when the title matched or the description did not.
 */
export function descriptionSnippet(
	title: string,
	description: string | null | undefined,
	query: string
): string | null {
	const q = foldText(query.trim());
	if (!q || !description || foldText(title).includes(q)) return null;
	const text = description.replace(/\s+/g, ' ').trim();
	const at = foldText(text).indexOf(q);
	// Folding can change a string's length (ligatures); the start is then a close guess
	if (at < 0) return null;
	const start = Math.max(0, at - SNIPPET_RADIUS);
	const end = Math.min(text.length, at + q.length + SNIPPET_RADIUS);
	return `${start > 0 ? '…' : ''}${text.slice(start, end).trim()}${end < text.length ? '…' : ''}`;
}

/** The server's scale, for rows the client ranks itself (pages, the collection in view). */
const RANK_SCORE = [100, 80, 60, 40] as const;

/** How well `name` matches `query`, on the same scale as the server's scores. */
export function localScore(name: string, query: string): number {
	return RANK_SCORE[matchRank(name, query)];
}

/**
 * Groups in the order to show them: the group holding the best match first, and where
 * matches tie, the order the current page asks for. Groups with nothing to show go last,
 * in page order, so a slow group does not move the rest when it arrives.
 */
export function orderGroups(
	pageOrder: PaletteGroup[],
	best: Partial<Record<PaletteGroup, number>>
): PaletteGroup[] {
	const rank = (key: PaletteGroup) => pageOrder.indexOf(key);
	const withHits = pageOrder.filter((key) => best[key] !== undefined);
	const without = pageOrder.filter((key) => best[key] === undefined);
	withHits.sort((a, b) => (best[b] ?? 0) - (best[a] ?? 0) || rank(a) - rank(b));
	return [...withHits, ...without];
}
