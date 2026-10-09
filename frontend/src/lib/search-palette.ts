import type { MatchContext } from '$lib/search-context';

export const SEARCH_RESULT_LIMIT = 8;
export const MAX_QUERY_LENGTH = 200;

/** Trimmed search text capped at {@link MAX_QUERY_LENGTH}; empty for a missing value. */
export function normaliseQuery(raw: string | null | undefined): string {
	return (raw ?? '').trim().slice(0, MAX_QUERY_LENGTH).trim();
}

/** The search string (`q=...`, for `/items?${...}`) that opens the items page with the text searched. */
export function seeAllSearch(query: string): string {
	return new URLSearchParams({ q: normaliseQuery(query) }).toString();
}

/** "Film · Director: Nolan": the type label and match context that are present. */
export function resultSubtitle(typeLabel: string | null, match: MatchContext | null): string {
	return [typeLabel, match ? `${match.label}: ${match.text}` : null].filter(Boolean).join(' · ');
}

/** The first row value from the first group that is not stale; '' when there is none. */
export function firstLiveValue(groups: { values: string[]; stale: boolean }[]): string {
	return groups.find((g) => !g.stale && g.values.length > 0)?.values[0] ?? '';
}

/**
 * The row the popup highlights by itself. It stays on "See all" until the items group has
 * answered, so a quick Enter never opens a row that is about to be pushed down.
 */
export function defaultHighlight(firstValue: string, itemsAnswered: boolean, seeAll: string) {
	return itemsAnswered && firstValue ? firstValue : seeAll;
}

export type PaletteView = 'hint' | 'idle' | 'loading' | 'results' | 'partial' | 'empty';

type PaletteState = {
	query: string;
	/** A search is waiting on its debounce or on at least one source. */
	pending: boolean;
	showSpinner: boolean;
	/** Rows shown across all groups. */
	count: number;
	/** Groups whose source failed and are not being retried. */
	failed: number;
};

/**
 * Which body the popup shows. Earlier results stay up while the next load is pending.
 * 'partial' means nothing was found but some sources failed, so their retry rows show.
 */
export function paletteView(state: PaletteState): PaletteView {
	if (!state.query.trim()) return 'hint';
	if (state.count > 0) return 'results';
	if (state.failed > 0 && !state.pending) return 'partial';
	if (state.pending) return state.showSpinner ? 'loading' : 'idle';
	return 'empty';
}

/** What a screen reader hears for the current body of the popup. `count` is the total across groups. */
export function liveMessage(view: PaletteView, query: string, count: number, failedGroups = 0) {
	switch (view) {
		case 'loading':
			return 'Searching';
		case 'empty':
			return `Nothing found for "${query.trim()}"`;
		case 'partial':
			return 'Some results could not be loaded';
		case 'results': {
			const total = count === 1 ? '1 result' : `${count} results`;
			return failedGroups > 0 ? `Some results could not be loaded. ${total}` : total;
		}
		default:
			return '';
	}
}
