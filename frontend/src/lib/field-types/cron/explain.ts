import cronstrue from 'cronstrue';
import { breakdownCron } from './breakdown';
import { unreachableReason } from './unreachable';

/** Plain-English reading of a cron expression, or why it cannot be read. */
export type CronExplanation = { ok: true; text: string } | { ok: false; reason: string };

const SHAPE = 'A schedule has five parts: minute, hour, day of month, month and day of week.';
const notSupported = (what: string) => `${what} is not supported here. Use * or a number instead.`;

/**
 * Quartz and AWS schedules start with a seconds part, which cron here does not have. When a
 * six-part schedule starts with 0, offer the five-part form: drop it and turn ? into *.
 */
function shapeReason(parts: string[]): string {
	if (parts.length !== 6 || parts[0] !== '0') return SHAPE;
	const suggestion = parts
		.slice(1)
		.map((part) => (part === '?' ? '*' : part))
		.join(' ');
	return `${SHAPE} If the first part is seconds, leave it out: ${suggestion}`;
}

function reasonFrom(error: unknown): string {
	const message = (error instanceof Error ? error.message : String(error)).replace(
		/^Error:\s*/,
		''
	);
	return message ? message.charAt(0).toUpperCase() + message.slice(1) + '.' : SHAPE;
}

const HOUR_LIST = /^\d+(,\d+)+$/;
const CLOCK_TIMES = /, at (\d{2}:00(?:(?:, and | and |, )\d{2}:00)*)/;

/**
 * cronstrue reads "every 5 minutes in hours 14 and 18" as "Every 5 minutes, at 14:00 and
 * 18:00", which sounds like two moments. When several minutes fall in a list of hours,
 * say the hours they fall in.
 */
function clarifyHours(text: string, minute: string, hour: string): string {
	if (/^\d+$/.test(minute) || !HOUR_LIST.test(hour)) return text;
	return text.replace(CLOCK_TIMES, ', during the $1 hours');
}

/**
 * Explain a cron expression in words, using 24-hour times. A list that mixes ranges or steps is
 * explained part by part, one line each, so show the text with `whitespace-pre-line`.
 *
 * An empty expression means the job is off, as it does on the server, and anything but
 * five parts is refused, as the scheduler does. The server's grammar is narrower than cronstrue's, so the forms it refuses
 * that cronstrue would still read (`?` and `W`) are turned away here too, as are ranges that run
 * backwards and days no chosen month has (31 February); see `unreachable.ts`.
 * `shared/contracts/cron-conformance.json` pins all of this against the server.
 */
export function explainCron(expression: string): CronExplanation {
	const trimmed = expression.trim();
	if (trimmed === '') return { ok: true, text: 'Never runs (off)' };
	const parts = trimmed.split(/\s+/);
	if (parts.length !== 5) return { ok: false, reason: shapeReason(parts) };
	if (trimmed.includes('?')) return { ok: false, reason: notSupported('"?"') };
	if (/w/i.test(parts[2])) {
		return { ok: false, reason: notSupported('"W" (nearest weekday)') };
	}
	try {
		// cronstrue splits on single spaces, the server on any whitespace.
		const sentence = cronstrue.toString(parts.join(' '), { use24HourTimeFormat: true });
		const unreachable = unreachableReason(parts);
		if (unreachable) return { ok: false, reason: unreachable };
		return { ok: true, text: breakdownCron(parts) ?? clarifyHours(sentence, parts[0], parts[1]) };
	} catch (error) {
		return { ok: false, reason: reasonFrom(error) };
	}
}
