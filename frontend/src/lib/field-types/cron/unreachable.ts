/**
 * The two ways a well-formed schedule can still be refused by the server: a range that runs
 * backwards (5-1, FRI-MON) and a day of the month that no chosen month has (31 February). The
 * rest of the grammar is cronstrue's to check.
 */

const MONTH_NAMES = [
	'JAN',
	'FEB',
	'MAR',
	'APR',
	'MAY',
	'JUN',
	'JUL',
	'AUG',
	'SEP',
	'OCT',
	'NOV',
	'DEC'
];
const WEEKDAY_NAMES = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
/** The longest each month can be, counting 29 February. */
const MONTH_LENGTHS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

type Part = { label: string; names: string[]; offset: number; min: number; max: number };

const MINUTE: Part = { label: 'minute', names: [], offset: 0, min: 0, max: 59 };
const HOUR: Part = { label: 'hour', names: [], offset: 0, min: 0, max: 23 };
const MONTH: Part = { label: 'month', names: MONTH_NAMES, offset: 1, min: 1, max: 12 };
const WEEKDAY: Part = { label: 'day of the week', names: WEEKDAY_NAMES, offset: 0, min: 0, max: 7 };
const DAY: Part = { label: 'day of the month', names: [], offset: 1, min: 1, max: 31 };

function toNumber(token: string, part: Part): number {
	const named = part.names.indexOf(token.toUpperCase());
	return named >= 0 ? named + part.offset : Number(token);
}

/** The values one comma item stands for, or the first backwards range in it. */
function expand(item: string, part: Part): { values: number[] } | { backwards: string } {
	const [range, step] = item.split('/');
	const [from, to] = range === '*' ? [String(part.min), String(part.max)] : range.split('-');
	const start = toNumber(from, part);
	const end = to === undefined ? (step === undefined ? start : part.max) : toNumber(to, part);
	if (end < start) return { backwards: range };
	const stride = Number(step ?? 1) || 1;
	const values: number[] = [];
	for (let value = start; value <= end; value += stride) values.push(value);
	return { values };
}

function valuesOf(field: string, part: Part): { values: Set<number> } | { backwards: string } {
	const values = new Set<number>();
	for (const item of field.split(',')) {
		const expanded = expand(item, part);
		if ('backwards' in expanded) return expanded;
		for (const value of expanded.values) values.add(value);
	}
	return { values };
}

/** Why the schedule can never run as written, or null when it can. `parts` is minute to weekday. */
export function unreachableReason(parts: string[]): string | null {
	// Last-day (L) and nth-weekday (#) forms are not plain lists of numbers; leave them to the server.
	if (parts.some((part) => /[^0-9A-Za-z*,/-]/.test(part))) return null;
	const found: Record<string, Set<number>> = {};
	for (const [index, part] of [MINUTE, HOUR, DAY, MONTH, WEEKDAY].entries()) {
		const result = valuesOf(parts[index], part);
		if ('backwards' in result) {
			return `"${result.backwards}" runs backwards in the ${part.label}. Put the smaller one first.`;
		}
		found[part.label] = result.values;
	}
	const days = found[DAY.label];
	const fits = [...found[MONTH.label]].some((month) =>
		[...days].some((day) => day <= MONTH_LENGTHS[month - 1])
	);
	return fits || days.size === 0 || found[MONTH.label].size === 0
		? null
		: 'No month in this schedule has that day of the month.';
}
