/**
 * Format a `YYYY-MM-DD` string as a local date. `new Date('YYYY-MM-DD')` parses as UTC
 * midnight and renders a day early in negative UTC offsets, so the time is pinned locally.
 */
export function formatIsoDate(value: string, month: 'long' | 'short'): string {
	const date = new Date(value + 'T00:00:00');
	if (isNaN(date.getTime())) return value;
	return date.toLocaleDateString(undefined, { year: 'numeric', month, day: 'numeric' });
}
