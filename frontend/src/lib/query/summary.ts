import { OPERATOR_LABELS, operatorTakesValue } from './operators';
import type { Condition, Operand, Value } from './types';

export type SummaryLookup = {
	typeLabel(slug: string): string;
	fieldLabel(type: string, key: string): string;
	/** A per-item field's label; when absent the key is used. */
	itemFieldLabel?(kind: string, key: string): string | null;
	/** Formats a plain value of a per-item field; null leaves the default text. */
	formatItemValue?(kind: string, key: string, value: unknown): string | null;
	/** A table column's label ("Cast › Role"); when absent the raw column key is used. */
	subFieldLabel?(type: string, key: string, subKey: string): string | null;
	/** The field's kind, so date fields read like the Added / Changed conditions. */
	fieldKind?(type: string, key: string, subKey: string | undefined): string | null;
	/** Formats a plain field value (not a `rel` or `ref`); null leaves the default text. */
	formatValue?(
		type: string,
		key: string,
		subKey: string | undefined,
		value: unknown
	): string | null;
};

const UNITS: Record<string, string> = { d: 'day', w: 'week', m: 'month', y: 'year' };

/** Words for the date operators against an absolute date or a future offset. */
const DATE_OPERATOR_WORDS: Record<string, string> = {
	'=': 'on',
	'>': 'after',
	'>=': 'on or after',
	'<': 'before',
	'<=': 'on or before'
};
const FUTURE_OPERATOR_WORDS: Record<string, string> = {
	'=': '',
	'>': 'after',
	'>=': 'on or after',
	'<': 'before',
	'<=': 'on or before'
};

const plural = (count: number, unit: string) => `${count} ${unit}${count === 1 ? '' : 's'}`;

function parseRel(rel: unknown): { count: number; unit: string; past: boolean } | null {
	const match = typeof rel === 'string' ? /^([+-]?)(\d+)([dwmy])$/.exec(rel) : null;
	if (!match) return null;
	return { count: Number(match[2]), unit: UNITS[match[3]], past: match[1] === '-' };
}

function isRec(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function safeJson(value: unknown): string {
	try {
		return JSON.stringify(value) ?? String(value);
	} catch {
		return String(value);
	}
}

/** One value as text: field references, money, booleans and plain scalars. */
function operandText(operand: Operand | unknown): string {
	if (typeof operand === 'boolean') return operand ? 'yes' : 'no';
	if (isRec(operand)) {
		if (typeof operand.ref === 'string') return operand.ref;
		if (typeof operand.rel === 'string') return operand.rel;
		if (typeof operand.value === 'number' && typeof operand.currency === 'string')
			return `${operand.value.toFixed(2)} ${operand.currency}`;
		return safeJson(operand);
	}
	if (Array.isArray(operand)) return operand.map(operandText).join(', ');
	return String(operand);
}

type Format = (operand: unknown) => string;

function valueText(op: string, value: Value | undefined, format: Format = operandText): string {
	if (value === undefined) return '';
	if (op === 'between' && Array.isArray(value) && value.length === 2)
		return `${format(value[0])} and ${format(value[1])}`;
	return Array.isArray(value) ? value.map(format).join(', ') : format(value);
}

/** Uses the lookup's formatter for plain operands; references and offsets stay as they are. */
function fieldFormat(c: Extract<Condition, { kind: 'field' }>, lookup: SummaryLookup): Format {
	return (operand) => {
		if (isRec(operand) && typeof operand.ref === 'string')
			return lookup.fieldLabel(c.type ?? '', operand.ref);
		const plain = !(isRec(operand) && ('ref' in operand || 'rel' in operand));
		if (plain) {
			try {
				const text =
					c.field_kind !== undefined
						? lookup.formatItemValue?.(c.field_kind, c.key, operand)
						: lookup.formatValue?.(c.type ?? '', c.key, c.sub_key, operand);
				if (typeof text === 'string') return text;
			} catch {
				// fall back to the default text
			}
		}
		return operandText(operand);
	};
}

function safe<T>(read: () => T): T | null {
	try {
		return read();
	} catch {
		return null;
	}
}

const DATE_KINDS = new Set(['date', 'partialdate']);

function describeField(c: Extract<Condition, { kind: 'field' }>, lookup: SummaryLookup): string {
	const itemKind = c.field_kind;
	const subKey = c.sub_key;
	let field: string;
	let kind: string | null | undefined;
	if (itemKind !== undefined) {
		field = safe(() => lookup.itemFieldLabel?.(itemKind, c.key)) || c.key;
		kind = itemKind;
	} else {
		const label = lookup.fieldLabel(c.type ?? '', c.key);
		const sub = subKey ? safe(() => lookup.subFieldLabel?.(c.type ?? '', c.key, subKey)) : null;
		field = subKey ? (sub ?? `${label} › ${subKey}`) : label;
		kind = safe(() => lookup.fieldKind?.(c.type ?? '', c.key, c.sub_key));
	}
	const head =
		itemKind === undefined
			? `${lookup.typeLabel(c.type ?? '')}: ${field}`
			: `Item field › ${field}:`;
	if (kind && DATE_KINDS.has(kind) && operatorTakesValue(c.op) && c.value !== undefined)
		return `${head} ${datePhrase(c.op, c.value, fieldFormat(c, lookup))}`;
	const op = OPERATOR_LABELS[c.op] ?? c.op;
	const value = operatorTakesValue(c.op) ? valueText(c.op, c.value, fieldFormat(c, lookup)) : '';
	return `${head} ${op}${value ? ` ${value}` : ''}`;
}

function relOf(operand: unknown): ReturnType<typeof parseRel> {
	return isRec(operand) ? parseRel(operand.rel) : null;
}

/** A date operand on its own, for the ends of a range. */
function dateEnd(operand: unknown, format: Format = operandText): string {
	const rel = relOf(operand);
	if (!rel) return format(operand);
	return rel.past
		? `${plural(rel.count, rel.unit)} ago`
		: `${plural(rel.count, rel.unit)} from now`;
}

function datePhrase(op: string, value: Value, format: Format = operandText): string {
	if (op === 'between' && Array.isArray(value) && value.length === 2)
		return `between ${dateEnd(value[0], format)} and ${dateEnd(value[1], format)}`;
	const rel = relOf(value);
	if (rel && rel.past) {
		const span = plural(rel.count, rel.unit);
		if (op === '>' || op === '>=')
			return rel.count === 1 ? `in the last ${rel.unit}` : `in the last ${span}`;
		if (op === '<' || op === '<=') return `more than ${span} ago`;
		return `${span} ago`;
	}
	if (rel) {
		const words = FUTURE_OPERATOR_WORDS[op] ?? OPERATOR_LABELS[op] ?? op;
		return `${words ? `${words} ` : ''}${plural(rel.count, rel.unit)} from now`;
	}
	const words = DATE_OPERATOR_WORDS[op] ?? OPERATOR_LABELS[op] ?? op;
	return `${words} ${valueText(op, value, format)}`.trim();
}

const TAG_MODES = { any: 'any of', all: 'all of', none: 'none of' } as const;

function listText(items: unknown): string {
	return Array.isArray(items) ? items.map(String).join(', ') : '';
}

function describe(c: Condition, lookup: SummaryLookup): string {
	switch (c.kind) {
		case 'field':
			return describeField(c, lookup);
		case 'date':
			return `${c.on === 'updated' ? 'Changed' : 'Added'} ${datePhrase(c.op, c.value)}`;
		case 'text':
			return `Contains “${c.q ?? ''}”`;
		case 'favourite':
			return c.value ? 'Is a favourite' : 'Is not a favourite';
		case 'tag': {
			const mode = TAG_MODES[c.mode] ?? TAG_MODES.any;
			return `Tag is ${mode} ${listText(c.tags)}`.trim();
		}
		case 'type': {
			const labels = (Array.isArray(c.in) ? c.in : []).map((slug) => lookup.typeLabel(slug));
			const last = labels.pop();
			if (last === undefined) return 'Type is any';
			return `Type is ${labels.length ? `${labels.join(', ')} or ` : ''}${last}`;
		}
		default:
			return 'Unknown filter';
	}
}

/** One-line description of a condition for a chip. Never throws. */
export function describeCondition(c: Condition, lookup: SummaryLookup): string {
	try {
		return describe(c, lookup);
	} catch {
		return 'Unreadable filter';
	}
}
