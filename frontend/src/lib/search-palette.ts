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

export type PaletteView = 'hint' | 'error' | 'idle' | 'loading' | 'results' | 'empty';

type PaletteState = {
	query: string;
	error: boolean;
	pending: boolean;
	showSpinner: boolean;
	count: number;
};

/** Which body the popup shows. Earlier results stay up while the next load is pending. */
export function paletteView(state: PaletteState): PaletteView {
	if (!state.query.trim()) return 'hint';
	if (state.error) return 'error';
	if (state.count > 0) return 'results';
	if (state.pending) return state.showSpinner ? 'loading' : 'idle';
	return 'empty';
}

/** What a screen reader hears for the current body of the popup. */
export function liveMessage(view: PaletteView, query: string, count: number, error: string | null) {
	switch (view) {
		case 'error':
			return error ?? 'Search failed';
		case 'loading':
			return 'Searching';
		case 'empty':
			return `No items match "${query.trim()}"`;
		case 'results':
			return count === 1 ? '1 result' : `${count} results`;
		default:
			return '';
	}
}
