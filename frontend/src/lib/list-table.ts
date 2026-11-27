/** What a list table shows in place of its rows, or `rows` when it shows them. */
export type ListTableState = 'error' | 'loading' | 'empty' | 'rows';

/**
 * Decides what a list table shows. The skeleton is for the first load only: while a sort,
 * search or page is read again the rows already there stay (dimmed), so the page does not
 * collapse and jump. The empty state waits for a finished read, so a list that is about to
 * fill never says it is empty.
 */
export function listTableState(list: {
	error: unknown;
	loading: boolean;
	rows: number;
}): ListTableState {
	if (list.error) return 'error';
	if (list.rows > 0) return 'rows';
	return list.loading ? 'loading' : 'empty';
}
