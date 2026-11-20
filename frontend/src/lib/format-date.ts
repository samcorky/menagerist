import { formatDistance } from 'date-fns';
import { preferences } from '$lib/preferences.svelte';

/**
 * The one place dates and times are written for people. Each function reads the person's
 * preferences (time zone, date order and clock) unless given them, so tests can pin them.
 * Calendar dates (`YYYY-MM-DD`, such as a release date) are never shifted by a time zone; only
 * timestamps are.
 */

export type DateOrder = 'automatic' | 'dmy' | 'mdy' | 'ymd';
export type Clock = 'automatic' | '12h' | '24h';
export type DateTimePrefs = {
	/** An IANA zone, or `browser` for the device's own. */
	zone: string;
	order: DateOrder;
	clock: Clock;
	/** The language for month names and the automatic styles; the browser's when unset. */
	locale?: string;
};

const ORDERS: readonly string[] = ['automatic', 'dmy', 'mdy', 'ymd'];
const CLOCKS: readonly string[] = ['automatic', '12h', '24h'];

/** The device's own time zone. */
export function browserZone(): string {
	return new Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** The signed-in person's date and time preferences, defaults where none is known. */
export function currentPrefs(): DateTimePrefs {
	const zone = preferences.value('datetime.time_zone');
	const order = preferences.value('datetime.date_order');
	const clock = preferences.value('datetime.clock');
	return {
		zone: typeof zone === 'string' && zone !== '' ? zone : 'browser',
		order: typeof order === 'string' && ORDERS.includes(order) ? (order as DateOrder) : 'automatic',
		clock: typeof clock === 'string' && CLOCKS.includes(clock) ? (clock as Clock) : 'automatic'
	};
}

/** The zone times are shown in: the chosen one, or the browser's. */
export function resolvedZone(prefs: DateTimePrefs = currentPrefs()): string {
	return prefs.zone === 'browser' ? browserZone() : prefs.zone;
}

/** Whether times should say their zone: only when it is not the device's own. */
function marksZone(prefs: DateTimePrefs): boolean {
	return prefs.zone !== 'browser' && prefs.zone !== browserZone();
}

function hourCycle(clock: Clock): Intl.DateTimeFormatOptions {
	if (clock === '12h') return { hourCycle: 'h12' };
	if (clock === '24h') return { hourCycle: 'h23' };
	return {};
}

/** A day, month and year in the chosen order; `timeZone` only for timestamps. */
function dateText(
	date: Date,
	month: 'long' | 'short',
	prefs: DateTimePrefs,
	timeZone?: string
): string {
	const options: Intl.DateTimeFormatOptions = { year: 'numeric', month, day: 'numeric', timeZone };
	if (prefs.order === 'automatic') {
		return new Intl.DateTimeFormat(prefs.locale, options).format(date);
	}
	if (prefs.order === 'ymd') {
		const parts = new Intl.DateTimeFormat('en-CA', {
			year: 'numeric',
			month: '2-digit',
			day: '2-digit',
			timeZone
		}).formatToParts(date);
		const part = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
		return `${part('year')}-${part('month')}-${part('day')}`;
	}
	const parts = new Intl.DateTimeFormat(prefs.locale, options).formatToParts(date);
	const part = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
	return prefs.order === 'dmy'
		? `${part('day')} ${part('month')} ${part('year')}`
		: `${part('month')} ${part('day')}, ${part('year')}`;
}

/** A time of day in the chosen clock, in `timeZone`, naming the zone when `mark` is set. */
function timeText(
	date: Date,
	prefs: DateTimePrefs,
	{ timeZone, mark, seconds = false }: { timeZone: string; mark: boolean; seconds?: boolean }
): string {
	return new Intl.DateTimeFormat(prefs.locale, {
		hour: 'numeric',
		minute: '2-digit',
		...(seconds ? { second: '2-digit' } : {}),
		...hourCycle(prefs.clock),
		timeZone,
		...(mark ? { timeZoneName: 'short' } : {})
	}).format(date);
}

/**
 * Format a `YYYY-MM-DD` string as a calendar date. `new Date('YYYY-MM-DD')` parses as UTC
 * midnight and renders a day early in negative UTC offsets, so the time is pinned locally, and
 * no time zone is applied: a release date is the same day everywhere.
 */
export function formatIsoDate(
	value: string,
	month: 'long' | 'short',
	prefs: DateTimePrefs = currentPrefs()
): string {
	const date = new Date(value + 'T00:00:00');
	if (isNaN(date.getTime())) return value;
	return dateText(date, month, prefs);
}

/**
 * Format a `YYYY`, `YYYY-MM` or `YYYY-MM-DD` string at the precision it was entered
 * ("1973", "Mar 1973", "14 Mar 1973"). A value that is not one of those is returned as is.
 */
export function formatPartialDate(
	value: string,
	month: 'long' | 'short',
	prefs: DateTimePrefs = currentPrefs()
): string {
	const parts = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/.exec(value);
	if (!parts) return value;
	const [, year, mm, dd] = parts;
	if (mm === undefined) return year;
	if (dd !== undefined) return formatIsoDate(value, month, prefs);
	if (prefs.order === 'ymd') return `${year}-${mm}`;
	const date = new Date(`${year}-${mm}-01T00:00:00`);
	if (isNaN(date.getTime())) return value;
	return new Intl.DateTimeFormat(prefs.locale, { year: 'numeric', month }).format(date);
}

/**
 * Format a UTC timestamp (e.g. `created_at`/`updated_at`) in the chosen zone, order and clock,
 * plus the equivalent UTC time for a tooltip.
 */
export function formatDateTime(
	value: string,
	options: { seconds?: boolean } = {},
	prefs: DateTimePrefs = currentPrefs()
): { local: string; utc: string } {
	const date = new Date(value);
	if (isNaN(date.getTime())) return { local: value, utc: value };
	const zone = resolvedZone(prefs);
	const seconds = options.seconds ?? false;
	const local = timeText(date, prefs, { timeZone: zone, mark: marksZone(prefs), seconds });
	const utc = timeText(date, prefs, { timeZone: 'UTC', mark: false, seconds });
	return {
		local: `${dateText(date, 'short', prefs, zone)}, ${local}`,
		utc: `${dateText(date, 'short', prefs, 'UTC')}, ${utc} UTC`
	};
}

/** A time of day alone ("14:05", or "2:05 pm"), in the chosen zone and clock. */
export function formatTime(value: string | Date, prefs: DateTimePrefs = currentPrefs()): string {
	const date = value instanceof Date ? value : new Date(value);
	if (isNaN(date.getTime())) return String(value);
	return timeText(date, prefs, { timeZone: resolvedZone(prefs), mark: marksZone(prefs) });
}

/** A zone's offset from UTC now, such as "GMT+1"; empty if the browser cannot say. */
export function zoneOffset(zone: string, now: Date = new Date()): string {
	try {
		const parts = new Intl.DateTimeFormat('en-GB', {
			timeZone: zone,
			timeZoneName: 'shortOffset'
		}).formatToParts(now);
		const offset = parts.find((part) => part.type === 'timeZoneName')?.value ?? '';
		return offset === 'GMT+0' ? 'GMT' : offset;
	} catch {
		return '';
	}
}

/** Every IANA zone the browser knows, or just its own where it cannot list them. */
export function knownZones(): string[] {
	const supported = (Intl as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf;
	return supported ? supported('timeZone') : [browserZone()];
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
