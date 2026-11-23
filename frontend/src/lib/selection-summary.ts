/** The bar's count line: what is selected, what the view hides, and when the limit stops it. */
export function selectionSummary(count: number, hidden: number, limit: number): string {
	if (count >= limit) return `${count} selected, the most one action takes`;
	if (hidden > 0) return `${count} selected, ${hidden} not shown by this search`;
	return `${count} selected`;
}

/** The Select all checkbox reflects the rows in view only. */
export function visibleCheckState(
	visibleSelected: number,
	visibleTotal: number
): 'unchecked' | 'indeterminate' | 'checked' {
	if (visibleTotal > 0 && visibleSelected >= visibleTotal) return 'checked';
	return visibleSelected > 0 ? 'indeterminate' : 'unchecked';
}
