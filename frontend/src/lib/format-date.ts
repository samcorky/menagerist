import { formatDistance } from 'date-fns';

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

/**
 * Format a UTC timestamp as "just now" / "about 2 hours ago", relative to `now`. Uses
 * `date-fns`'s `formatDistance` for its more conversational wording ("about", "over", "almost")
 * than a bare `Intl.RelativeTimeFormat` count; English only, no locale switching. Within 30
 * seconds either way is "just now" rather than date-fns' own "less than a minute ago".
 *
 * `value` (a `created_at`/`updated_at`) is always in the past from the server's perspective, so
 * a positive difference is clamped to "just now" rather than shown as "in X" - it can only be a
 * client/server clock drift or (most commonly) `now` not yet having ticked forward since a save
 * produced a fresher timestamp than the caller's last-refreshed `now`, never a real future date.
 */
export function formatRelativeTime(value: string, now: Date = new Date()): string {
	const date = new Date(value);
	if (isNaN(date.getTime())) return value;
	const diffMs = date.getTime() - now.getTime();
	if (diffMs > 0 || Math.abs(diffMs) < 30_000) return 'just now';
	return formatDistance(date, now, { addSuffix: true });
}
