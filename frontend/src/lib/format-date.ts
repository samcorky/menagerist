/**
 * Format a `YYYY-MM-DD` string as a local date. `new Date('YYYY-MM-DD')` parses as UTC
 * midnight and renders a day early in negative UTC offsets, so the time is pinned locally.
 */
export function formatIsoDate(value: string, month: 'long' | 'short'): string {
	const date = new Date(value + 'T00:00:00');
	if (isNaN(date.getTime())) return value;
	return date.toLocaleDateString(undefined, { year: 'numeric', month, day: 'numeric' });
}

const DATE_TIME_OPTS: Intl.DateTimeFormatOptions = {
	year: 'numeric',
	month: 'short',
	day: 'numeric',
	hour: 'numeric',
	minute: '2-digit'
};

/**
 * Format a UTC timestamp (e.g. `created_at`/`updated_at`) in the browser's own locale and
 * time zone, plus the equivalent UTC time for a tooltip.
 */
export function formatDateTime(value: string): { local: string; utc: string } {
	const date = new Date(value);
	if (isNaN(date.getTime())) return { local: value, utc: value };
	return {
		local: date.toLocaleString(undefined, DATE_TIME_OPTS),
		utc: `${date.toLocaleString(undefined, { ...DATE_TIME_OPTS, timeZone: 'UTC' })} UTC`
	};
}

const RELATIVE_UNITS: { unit: Intl.RelativeTimeFormatUnit; ms: number }[] = [
	{ unit: 'year', ms: 365 * 24 * 60 * 60 * 1000 },
	{ unit: 'month', ms: 30 * 24 * 60 * 60 * 1000 },
	{ unit: 'week', ms: 7 * 24 * 60 * 60 * 1000 },
	{ unit: 'day', ms: 24 * 60 * 60 * 1000 },
	{ unit: 'hour', ms: 60 * 60 * 1000 },
	{ unit: 'minute', ms: 60 * 1000 }
];

/** Format a UTC timestamp as "just now" / "3 hours ago" / "in 2 days", relative to `now`. */
export function formatRelativeTime(value: string, now: Date = new Date()): string {
	const date = new Date(value);
	if (isNaN(date.getTime())) return value;
	const diffMs = date.getTime() - now.getTime();
	if (Math.abs(diffMs) < 45_000) return 'Just now';

	const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
	for (const { unit, ms } of RELATIVE_UNITS) {
		if (Math.abs(diffMs) >= ms || unit === 'minute') {
			return rtf.format(Math.round(diffMs / ms), unit);
		}
	}
	return rtf.format(0, 'minute');
}
