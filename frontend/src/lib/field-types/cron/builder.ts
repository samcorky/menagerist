/**
 * A schedule said as a sentence ("Every Monday at 09:30"), and the cron it stands for.
 *
 * Only the common shapes have a sentence. Anything else is a custom schedule, which
 * the cron box handles and explains.
 */

export const MINUTE_STEPS = [5, 10, 15, 20, 30] as const;
export type MinuteStep = (typeof MINUTE_STEPS)[number];

/** Cron numbers the days of the week from Sunday (0). Listed from Monday. */
export const WEEKDAYS = [
	{ value: 1, label: 'Monday' },
	{ value: 2, label: 'Tuesday' },
	{ value: 3, label: 'Wednesday' },
	{ value: 4, label: 'Thursday' },
	{ value: 5, label: 'Friday' },
	{ value: 6, label: 'Saturday' },
	{ value: 0, label: 'Sunday' }
] as const;

/** Days 29 to 31 are left out: they would skip some months. */
export const LAST_DAY_OF_MONTH_CHOICE = 28;

export type Sentence =
	| { kind: 'off' }
	| { kind: 'minutes'; every: MinuteStep }
	| { kind: 'hourly'; minute: number }
	| { kind: 'daily'; hour: number; minute: number }
	| { kind: 'weekdays'; hour: number; minute: number }
	| { kind: 'weekly'; day: number; hour: number; minute: number }
	| { kind: 'monthly'; dayOfMonth: number; hour: number; minute: number };

export type SentenceKind = Sentence['kind'];

/** The choices for the first dropdown, in the order they are offered. */
export const SENTENCE_KINDS: { kind: SentenceKind; label: string }[] = [
	{ kind: 'daily', label: 'Every day' },
	{ kind: 'weekdays', label: 'Every weekday (Monday to Friday)' },
	{ kind: 'weekly', label: 'Every week' },
	{ kind: 'monthly', label: 'Every month' },
	{ kind: 'hourly', label: 'Every hour' },
	{ kind: 'minutes', label: 'Every few minutes' },
	{ kind: 'off', label: 'Never (off)' }
];

/** A sentence of the given kind with sensible values, for when the kind changes. */
export function defaultSentence(kind: SentenceKind): Sentence {
	switch (kind) {
		case 'off':
			return { kind };
		case 'minutes':
			return { kind, every: 15 };
		case 'hourly':
			return { kind, minute: 0 };
		case 'daily':
		case 'weekdays':
			return { kind, hour: 3, minute: 0 };
		case 'weekly':
			return { kind, day: 1, hour: 3, minute: 0 };
		case 'monthly':
			return { kind, dayOfMonth: 1, hour: 3, minute: 0 };
	}
}

/** The sentence for a newly chosen kind, keeping the time of day if both kinds have one. */
export function switchKind(current: Sentence | null, kind: SentenceKind): Sentence {
	const next = defaultSentence(kind);
	if (current && 'hour' in current && 'hour' in next) {
		return { ...next, hour: current.hour, minute: current.minute };
	}
	return next;
}

/** The five-part cron expression for a sentence; an empty string when off. */
export function buildCron(sentence: Sentence): string {
	switch (sentence.kind) {
		case 'off':
			return '';
		case 'minutes':
			return `*/${sentence.every} * * * *`;
		case 'hourly':
			return `${sentence.minute} * * * *`;
		case 'daily':
			return `${sentence.minute} ${sentence.hour} * * *`;
		case 'weekdays':
			return `${sentence.minute} ${sentence.hour} * * 1-5`;
		case 'weekly':
			return `${sentence.minute} ${sentence.hour} * * ${sentence.day}`;
		case 'monthly':
			return `${sentence.minute} ${sentence.hour} ${sentence.dayOfMonth} * *`;
	}
}

function whole(part: string, min: number, max: number): number | null {
	if (!/^\d{1,2}$/.test(part)) return null;
	const value = Number(part);
	return value >= min && value <= max ? value : null;
}

/** The sentence a cron expression says, or null when it is a custom schedule. */
export function parseCron(expression: string): Sentence | null {
	const trimmed = expression.trim();
	if (trimmed === '') return { kind: 'off' };
	const parts = trimmed.split(/\s+/);
	if (parts.length !== 5) return null;
	const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
	if (month !== '*') return null;

	const step = /^\*\/(\d{1,2})$/.exec(minute);
	if (step && hour === '*' && dayOfMonth === '*' && dayOfWeek === '*') {
		const every = Number(step[1]);
		return (MINUTE_STEPS as readonly number[]).includes(every)
			? { kind: 'minutes', every: every as MinuteStep }
			: null;
	}

	const m = whole(minute, 0, 59);
	if (m === null) return null;
	if (hour === '*') {
		return dayOfMonth === '*' && dayOfWeek === '*' ? { kind: 'hourly', minute: m } : null;
	}
	const h = whole(hour, 0, 23);
	if (h === null) return null;

	if (dayOfMonth === '*' && dayOfWeek === '*') return { kind: 'daily', hour: h, minute: m };
	if (dayOfMonth === '*' && dayOfWeek === '1-5') {
		return { kind: 'weekdays', hour: h, minute: m };
	}
	if (dayOfMonth === '*') {
		const day = whole(dayOfWeek, 0, 7);
		return day === null ? null : { kind: 'weekly', day: day % 7, hour: h, minute: m };
	}
	if (dayOfWeek === '*') {
		const day = whole(dayOfMonth, 1, LAST_DAY_OF_MONTH_CHOICE);
		return day === null ? null : { kind: 'monthly', dayOfMonth: day, hour: h, minute: m };
	}
	return null;
}

/** "03:05" for the time inputs, and back. */
export function formatTime(hour: number, minute: number): string {
	return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

export function parseTime(value: string): { hour: number; minute: number } | null {
	const match = /^(\d{2}):(\d{2})$/.exec(value);
	if (!match) return null;
	const hour = Number(match[1]);
	const minute = Number(match[2]);
	return hour <= 23 && minute <= 59 ? { hour, minute } : null;
}

/** 1 becomes "1st", 12 "12th", 23 "23rd". */
export function ordinal(n: number): string {
	const tens = n % 100;
	if (tens >= 11 && tens <= 13) return `${n}th`;
	const suffix = { 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] ?? 'th';
	return `${n}${suffix}`;
}
