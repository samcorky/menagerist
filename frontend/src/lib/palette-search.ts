import type { RouteId } from '$app/types';

export const GROUP_CAPS = { items: 5, collections: 3, itemTypes: 3, pages: 4 } as const;

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
	const n = name.toLowerCase();
	const q = query.trim().toLowerCase();
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

const contains = (text: string, needle: string) => text.toLowerCase().includes(needle);

/** App pages whose label or keyword contains the query, best first. */
export function matchPages(query: string): PalettePage[] {
	const q = query.trim().toLowerCase();
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
	query: string
): T[] {
	const q = query.trim().toLowerCase();
	if (!q) return [];
	const hits = types.filter((t) => contains(t.label, q) || contains(t.slug, q));
	return rankByName(hits, q, (t) => t.label).slice(0, GROUP_CAPS.itemTypes);
}
