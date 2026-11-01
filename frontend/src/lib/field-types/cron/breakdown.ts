/**
 * A part-by-part reading for schedules that cronstrue turns into a run-on sentence: a comma list
 * in which some item is a range or a step ("7-59/13,*\/17,2"). Plain lists, single ranges and
 * single steps still read well as sentences, so those keep cronstrue's wording.
 */

const MONTHS = [
	'January',
	'February',
	'March',
	'April',
	'May',
	'June',
	'July',
	'August',
	'September',
	'October',
	'November',
	'December'
];
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

type Part = {
	label: string;
	unit: { one: string; many: string };
	/** Names a value: 2 becomes February, MON becomes Monday. */
	name: (value: string) => string;
};

const byNumber = (names: string[], offset: number) => (value: string) => {
	if (/^\d+$/.test(value)) return names[(Number(value) - offset) % names.length] ?? value;
	const abbreviation = value.slice(0, 3).toLowerCase();
	return names.find((name) => name.slice(0, 3).toLowerCase() === abbreviation) ?? value;
};
const plain = (value: string) => value;

const PARTS: Part[] = [
	{ label: 'Minute', unit: { one: 'minute', many: 'minutes' }, name: plain },
	{ label: 'Hour', unit: { one: 'hour', many: 'hours' }, name: plain },
	{ label: 'Day of month', unit: { one: 'day', many: 'days' }, name: plain },
	{ label: 'Month', unit: { one: 'month', many: 'months' }, name: byNumber(MONTHS, 1) },
	{ label: 'Day of week', unit: { one: 'day', many: 'days' }, name: byNumber(WEEKDAYS, 0) }
];

function describeItem(item: string, part: Part): string {
	const [range, step] = item.split('/');
	const [from, to] = range.split('-');
	const every =
		!step || step === '1' ? `every ${part.unit.one}` : `every ${step} ${part.unit.many}`;
	if (range === '*') return every;
	const start = part.name(from);
	const span = to === undefined ? start : `${start} to ${part.name(to)}`;
	if (step === undefined) return span;
	return to === undefined ? `${every} (starting at ${start})` : `${every} from ${span}`;
}

function joinItems(items: string[]): string {
	return items.length < 2
		? (items[0] ?? '')
		: `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`;
}

/** Whether a part is a list that mixes in ranges or steps, which is where cronstrue loses the thread. */
function isMixedList(field: string): boolean {
	const items = field.split(',');
	return items.length > 1 && items.some((item) => /[-/]/.test(item));
}

/** One line per part that is not `*`, or null when every part reads well as a sentence. */
export function breakdownCron(fields: string[]): string | null {
	if (!fields.some(isMixedList)) return null;
	const lines = fields.flatMap((field, index) =>
		field === '*'
			? []
			: `${PARTS[index].label}: ${joinItems(field.split(',').map((item) => describeItem(item, PARTS[index])))}`
	);
	// Cron runs a schedule on a day that fits either the date or the weekday, never both.
	if (fields[2] !== '*' && fields[4] !== '*') {
		lines.push('A day counts if it fits the day of the month or the day of the week.');
	}
	return lines.join('\n');
}
