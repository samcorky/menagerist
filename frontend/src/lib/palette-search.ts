import type { RouteId } from '$app/types';
import { foldText } from '$lib/fold-text';
import { groupLabel, settingId } from '$lib/settings-form';
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

/** Item types whose label or slug contains the query, best first. */
export function matchItemTypes<T extends { label: string; slug: string }>(
	types: T[],
	query: string,
	cap: number = GROUP_CAPS.itemTypes
): T[] {
	const q = foldText(query.trim());
	if (!q) return [];
	const hits = types.filter((t) => contains(t.label, q) || contains(t.slug, q));
	return rankByName(hits, q, (t) => t.label).slice(0, cap);
}

export type PaletteSetting = {
	key: string;
	group: string;
	title: string;
	description: string | null;
};
export type PaletteTask = { job_key: string; title: string; description: string };

/** Settings whose title, description or section name contains the query, best title first. */
export function matchSettings<T extends PaletteSetting>(
	settings: T[],
	query: string,
	cap: number = GROUP_CAPS.settings
): T[] {
	const q = foldText(query.trim());
	if (!q) return [];
	const hits = settings.filter(
		(s) =>
			contains(s.title, q) || contains(s.description ?? '', q) || contains(groupLabel(s.group), q)
	);
	return rankByName(hits, q, (s) => s.title).slice(0, cap);
}

/** Scheduled tasks whose title or description contains the query, best title first. */
export function matchTasks<T extends PaletteTask>(
	tasks: T[],
	query: string,
	cap: number = GROUP_CAPS.tasks
): T[] {
	const q = foldText(query.trim());
	if (!q) return [];
	const hits = tasks.filter((t) => contains(t.title, q) || contains(t.description, q));
	return rankByName(hits, q, (t) => t.title).slice(0, cap);
}

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
	if (order[0]) caps[order[0]] += LEAD_BONUS;
	return { order, collection, caps };
}
