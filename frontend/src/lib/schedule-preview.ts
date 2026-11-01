import { previewSchedule } from '$lib/api/client';
import { explainCron } from '$lib/field-types/cron/explain';

/** When a schedule would next run: UTC instants and the zone the schedule is read in. */
export type SchedulePreview = { timezone: string; runs: string[] };

/**
 * One run in the instance's own zone, in 24-hour time: "Thu 29 Oct, 03:00". The year is
 * added when it is not this year, so a distant run is not mistaken for a near one.
 */
export function formatRun(iso: string, timeZone: string, now: Date = new Date()): string {
	const when = new Date(iso);
	const year = (date: Date) =>
		new Intl.DateTimeFormat('en-GB', { year: 'numeric', timeZone }).format(date);
	const parts = new Intl.DateTimeFormat('en-GB', {
		weekday: 'short',
		day: 'numeric',
		month: 'short',
		...(year(when) === year(now) ? {} : { year: 'numeric' as const }),
		hour: '2-digit',
		minute: '2-digit',
		hourCycle: 'h23',
		timeZone
	}).formatToParts(when);
	const part = (type: Intl.DateTimeFormatPartTypes) =>
		parts.find((p) => p.type === type)?.value ?? '';
	const date = [part('weekday'), part('day'), part('month'), part('year')]
		.filter(Boolean)
		.join(' ');
	return `${date}, ${part('hour')}:${part('minute')}`;
}

/** The runs still to come: a cached answer may have its first run already behind it. */
export function upcoming(preview: SchedulePreview, now: Date = new Date()): string[] {
	return preview.runs.filter((run) => new Date(run).getTime() > now.getTime());
}

export type NextRuns = { next: string; later: string[]; timezone: string } | null;

/** The next run and the few after it, ready to show; null when nothing is due. */
export function nextRuns(preview: SchedulePreview, now: Date = new Date()): NextRuns {
	const [first, ...rest] = upcoming(preview, now);
	if (!first) return null;
	const format = (iso: string) => formatRun(iso, preview.timezone, now);
	return { next: format(first), later: rest.map(format), timezone: preview.timezone };
}

/** Answers are kept briefly so several widgets showing one schedule ask once. */
export const PREVIEW_TTL_MS = 30_000;

type Fetch = (expression: string) => Promise<SchedulePreview | 'unavailable' | Error>;

/** Ask the server when an expression would next run. */
export const fetchPreview: Fetch = async (expression) => {
	const result = await previewSchedule({ query: { expression, count: 3 } });
	if (result.response?.status === 403) return 'unavailable';
	if (result.error || !result.data) {
		return new Error(
			typeof (result.error as { detail?: unknown } | undefined)?.detail === 'string'
				? String((result.error as { detail: string }).detail)
				: 'Could not work out the next run.'
		);
	}
	return { timezone: result.data.timezone, runs: result.data.runs };
};

/** A small cache in front of a fetch, keyed by the trimmed expression. */
export class PreviewCache {
	#entries = new Map<string, { at: number; value: SchedulePreview | 'unavailable' | Error }>();
	#inflight = new Map<string, Promise<SchedulePreview | 'unavailable' | Error>>();

	constructor(
		private readonly load: Fetch = fetchPreview,
		private readonly clock: () => number = Date.now
	) {}

	async get(expression: string): Promise<SchedulePreview | 'unavailable' | Error> {
		const key = expression.trim();
		const hit = this.#entries.get(key);
		if (hit && this.clock() - hit.at < PREVIEW_TTL_MS && !(hit.value instanceof Error)) {
			return hit.value;
		}
		const pending = this.#inflight.get(key);
		if (pending) return pending;
		const request = this.load(key)
			.then((value) => {
				if (!(value instanceof Error)) this.#entries.set(key, { at: this.clock(), value });
				return value;
			})
			.catch((error: unknown) =>
				error instanceof Error ? error : new Error('Could not work out the next run.')
			)
			.finally(() => this.#inflight.delete(key));
		this.#inflight.set(key, request);
		return request;
	}
}

/** The shared cache the schedule widgets ask through. */
export const previewCache = new PreviewCache();

/**
 * Whether an expression needs the server: an empty one means off, and one the browser
 * already cannot read is not worth asking about (the widget says why).
 */
export function previewPlan(expression: string): 'off' | 'skip' | 'fetch' {
	if (expression.trim() === '') return 'off';
	return explainCron(expression).ok ? 'fetch' : 'skip';
}
