import cronstrue from 'cronstrue';

/** Plain-English reading of a cron expression, or why it cannot be read. */
export type CronExplanation = { ok: true; text: string } | { ok: false; reason: string };

const SHAPE = 'A schedule has five parts: minute, hour, day of month, month and day of week.';
const notSupported = (what: string) => `${what} is not supported here. Use * or a number instead.`;

function reasonFrom(error: unknown): string {
	const message = (error instanceof Error ? error.message : String(error)).replace(
		/^Error:\s*/,
		''
	);
	return message ? message.charAt(0).toUpperCase() + message.slice(1) + '.' : SHAPE;
}

/**
 * Explain a cron expression in words, using 24-hour times.
 *
 * An empty expression means the job is off, as it does on the server, and anything but
 * five parts is refused, as the scheduler does. The server's grammar is narrower than cronstrue's, so the forms it refuses
 * that cronstrue would still read (`?` and `W`) are turned away here too. A schedule
 * that is well formed but can never fire (31 February) is only the server's to catch;
 * `shared/contracts/cron-conformance.json` records that limit.
 */
export function explainCron(expression: string): CronExplanation {
	const trimmed = expression.trim();
	if (trimmed === '') return { ok: true, text: 'Never runs (off)' };
	const parts = trimmed.split(/\s+/);
	if (parts.length !== 5) return { ok: false, reason: SHAPE };
	if (trimmed.includes('?')) return { ok: false, reason: notSupported('"?"') };
	if (/w/i.test(parts[2])) {
		return { ok: false, reason: notSupported('"W" (nearest weekday)') };
	}
	try {
		return {
			ok: true,
			// cronstrue splits on single spaces, the server on any whitespace.
			text: cronstrue.toString(parts.join(' '), { use24HourTimeFormat: true })
		};
	} catch (error) {
		return { ok: false, reason: reasonFrom(error) };
	}
}
