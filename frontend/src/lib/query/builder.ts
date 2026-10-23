import { decodeQuery, encodeQuery } from './codec';
import {
	findField,
	findItemField,
	ITEM_FIELDS_CAP,
	itemFieldGroup,
	itemFieldInfo,
	itemFieldSubject,
	parseItemFieldSubject,
	type Catalogue,
	type FieldInfo
} from './fields';
import type { ComboboxItem } from '$lib/components/ui/combobox/combobox';
import {
	LIST_OPERATORS,
	OPERATOR_LABELS,
	operatorsForCondition,
	operatorsForKind,
	operatorTakesValue
} from './operators';
import { describeCondition, type SummaryLookup } from './summary';
import { pathKey } from './warnings';
import {
	isGroup,
	MAX_COLLECTION_IDS,
	MAX_TEXT_LENGTH,
	type Condition,
	type Group,
	type MediaType,
	type Node,
	type Operand,
	type Path,
	type Query,
	type SortKey,
	type Value
} from './types';

/*
 * Pure helpers behind the filter builder. The builder edits a draft tree that may hold
 * unfinished rows (no field chosen yet, a value still being typed); `applyDraft` drops those
 * so only conditions the server can run reach the URL.
 */

type FieldCondition = Extract<Condition, { kind: 'field' }>;

export { itemFieldSubject, parseItemFieldSubject };
type DateCondition = Extract<Condition, { kind: 'date' }>;

export type Subject =
	| 'blank'
	| 'text'
	| 'type'
	| 'favourite'
	| 'tag'
	| 'created'
	| 'updated'
	| 'collection'
	| 'media'
	| 'name'
	| 'description';

const SUBJECT_LABELS: Record<Exclude<Subject, 'blank'>, string> = {
	type: 'Type',
	favourite: 'Favourite',
	tag: 'Tags',
	created: 'Added',
	updated: 'Changed',
	text: 'Text',
	collection: 'In collection',
	media: 'Media',
	name: 'Name',
	description: 'Description'
};

const CONTENT_SUBJECTS: ReadonlySet<string> = new Set([
	'collection',
	'media',
	'name',
	'description'
]);

export const GENERAL_SUBJECTS = (
	Object.keys(SUBJECT_LABELS) as (keyof typeof SUBJECT_LABELS)[]
).map((value) => ({
	value,
	label: SUBJECT_LABELS[value],
	group: CONTENT_SUBJECTS.has(value) ? 'Content' : 'Any item'
}));

export function fieldSubject(type: string, key: string, subKey?: string): string {
	return `field:${JSON.stringify([type, key, subKey ?? null])}`;
}

export function parseFieldSubject(
	subject: string
): { type: string; key: string; subKey?: string } | null {
	if (!subject.startsWith('field:')) return null;
	try {
		const parsed: unknown = JSON.parse(subject.slice('field:'.length));
		if (!Array.isArray(parsed) || typeof parsed[0] !== 'string' || typeof parsed[1] !== 'string')
			return null;
		return typeof parsed[2] === 'string'
			? { type: parsed[0], key: parsed[1], subKey: parsed[2] }
			: { type: parsed[0], key: parsed[1] };
	} catch {
		return null;
	}
}

/** A row whose subject has not been chosen yet. Never sent. */
export function blankCondition(): Condition {
	return { kind: 'field', type: '', key: '', op: '' };
}

export function isBlank(c: Condition): boolean {
	return c.kind === 'field' && c.type === '' && c.key === '';
}

export function subjectOf(c: Condition): string {
	switch (c.kind) {
		case 'field':
			if (isBlank(c)) return 'blank';
			return c.field_kind !== undefined
				? itemFieldSubject(c.field_kind, c.key)
				: fieldSubject(c.type ?? '', c.key, c.sub_key);
		case 'date':
			return c.on === 'updated' ? 'updated' : 'created';
		default:
			return c.kind;
	}
}

/** The field a row is about. A per-item field is read from the row's own kind. */
export function fieldOf(c: Condition, catalogue: Catalogue): FieldInfo | undefined {
	if (c.kind !== 'field' || isBlank(c)) return undefined;
	if (c.field_kind !== undefined) return itemFieldInfo(catalogue, c.field_kind, c.key);
	return findField(catalogue, c.type ?? '', c.key, c.sub_key);
}

const LAST_30_DAYS = { rel: '-30d' };

/** A fresh condition for a subject: the first operator and no value yet. */
export function conditionFor(subject: string, catalogue: Catalogue): Condition {
	switch (subject) {
		case 'text':
			return { kind: 'text', q: '' };
		case 'type':
			return { kind: 'type', in: [] };
		case 'favourite':
			return { kind: 'favourite', value: true };
		case 'tag':
			return { kind: 'tag', mode: 'any', tags: [] };
		case 'description':
			return { kind: 'description', op: '~', value: '' };
		case 'name':
			return { kind: 'name', op: '~', value: '' };
		case 'media':
			return { kind: 'media', mode: 'has' };
		case 'collection':
			return { kind: 'collection', mode: 'any', in: [] };
		case 'created':
		case 'updated':
			return { kind: 'date', on: subject, op: '>=', value: LAST_30_DAYS };
	}
	const item = parseItemFieldSubject(subject);
	if (item) {
		return operatorsForKind(item.kind).length > 0
			? { kind: 'field', field_kind: item.kind, key: item.key, op: operatorsForKind(item.kind)[0] }
			: blankCondition();
	}
	const ref = parseFieldSubject(subject);
	const field = ref ? findField(catalogue, ref.type, ref.key, ref.subKey) : undefined;
	if (!ref || !field) return blankCondition();
	const out: FieldCondition = {
		kind: 'field',
		type: ref.type,
		key: ref.key,
		op: operatorsForKind(field.kind)[0] ?? '='
	};
	if (ref.subKey) out.sub_key = ref.subKey;
	return out;
}

/** Change what a row is about. A different subject or kind resets the operator and value. */
export function withSubject(c: Condition, subject: string, catalogue: Catalogue): Condition {
	if (subject === subjectOf(c)) return c;
	return conditionFor(subject, catalogue);
}

export type ValueShape = 'none' | 'single' | 'range' | 'multi' | 'list' | 'boolean';

const TEXT_KINDS = new Set(['text', 'url', 'email', 'phone', 'longtext']);

/** Which value input a field condition needs. */
export function valueShape(kind: string, op: string): ValueShape {
	if (!operatorTakesValue(op)) return 'none';
	if (op === 'between') return 'range';
	if (LIST_OPERATORS.has(op)) return TEXT_KINDS.has(kind) ? 'list' : 'multi';
	if (op === 'has') return 'multi';
	if (kind === 'boolean') return 'boolean';
	return 'single';
}

export const DATE_OPERATORS = ['>=', '<=', '=', '>', '<', 'between'] as const;

const DATE_LABELS: Record<string, string> = {
	'=': 'is on',
	'!=': 'is not on',
	'>': 'is after',
	'>=': 'is on or after',
	'<': 'is before',
	'<=': 'is on or before',
	between: 'is between'
};

export function operatorLabel(kind: string, op: string): string {
	if (kind === 'date' || kind === 'partialdate')
		return DATE_LABELS[op] ?? OPERATOR_LABELS[op] ?? op;
	return OPERATOR_LABELS[op] ?? op;
}

export const MEDIA_MODES = [
	{ value: 'has', label: 'has' },
	{ value: 'none', label: 'has no' }
] as const;

/** What kind of media a media row asks about; `any` leaves out the condition's `type`. */
export const MEDIA_TYPES = [
	{ value: 'any', label: 'media' },
	{ value: 'image', label: 'an image' },
	{ value: 'document', label: 'a document' }
] as const;

export const COLLECTION_MODES = [
	{ value: 'any', label: 'is in any of' },
	{ value: 'none', label: 'is in none of' }
] as const;

export function withMediaMode(c: Condition, mode: 'has' | 'none'): Condition {
	return c.kind === 'media' ? { ...c, mode } : c;
}

/** Narrow a media row to images or documents; null means any media. */
export function withMediaType(c: Condition, type: MediaType | null): Condition {
	if (c.kind !== 'media') return c;
	const { type: _old, ...rest } = c;
	return type === null ? rest : { ...rest, type };
}

export function withCollectionMode(c: Condition, mode: 'any' | 'none'): Condition {
	return c.kind === 'collection' ? { ...c, mode } : c;
}

/** Set the collections a row names: duplicates dropped, at most 50 kept. */
export function withCollectionIds(c: Condition, ids: readonly string[]): Condition {
	if (c.kind !== 'collection') return c;
	return { ...c, in: [...new Set(ids)].slice(0, MAX_COLLECTION_IDS) };
}

export const TAG_MODES = [
	{ value: 'any', label: 'has any of' },
	{ value: 'all', label: 'has all of' },
	{ value: 'none', label: 'has none of' }
] as const;

function emptyValueFor(shape: ValueShape): Value | undefined {
	if (shape === 'range') return ['', ''];
	if (shape === 'multi' || shape === 'list') return [];
	return undefined;
}

/** Change a field or date condition's operator, keeping the value when its shape still fits. */
export function withOperator(c: Condition, op: string, catalogue: Catalogue): Condition {
	if (c.kind === 'description' || c.kind === 'name') {
		if (op === c.op || !operatorsForCondition(c.kind).includes(op)) return c;
		if (!operatorTakesValue(op)) return { kind: c.kind, op } as Condition;
		return { kind: c.kind, op, value: c.value ?? '' } as Condition;
	}
	if (c.kind === 'date') {
		const wasRange = c.op === 'between';
		const isRange = op === 'between';
		if (wasRange === isRange) return { ...c, op };
		return { ...c, op, value: isRange ? ['', ''] : LAST_30_DAYS };
	}
	if (c.kind !== 'field' || isBlank(c)) return c;
	const kind = fieldOf(c, catalogue)?.kind ?? '';
	const before = valueShape(kind, c.op);
	const after = valueShape(kind, op);
	const { value: _old, ...rest } = c;
	const next: FieldCondition = { ...rest, op };
	if (after === 'none') return next;
	const value = before === after ? c.value : emptyValueFor(after);
	if (value !== undefined) next.value = value;
	return next;
}

function isRec(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function isRef(value: unknown): value is { ref: string } {
	return isRec(value) && typeof value.ref === 'string';
}

export function isRel(value: unknown): value is { rel: string } {
	return isRec(value) && typeof value.rel === 'string';
}

const NUMERIC = /^-?\d+(\.\d+)?$/;
const NUMBER_KINDS = new Set(['number', 'rating', 'duration']);

/** A field widget's output as a query operand; undefined when the input is empty. */
export function fromWidget(kind: string, raw: unknown): Operand | undefined {
	if (raw === undefined || raw === null || raw === '') return undefined;
	if (NUMBER_KINDS.has(kind)) {
		if (typeof raw === 'number') return raw;
		const text = String(raw).trim();
		return NUMERIC.test(text) ? Number(text) : text;
	}
	if (kind === 'money') {
		if (!isRec(raw)) return undefined;
		const amount = raw.value === undefined || raw.value === null ? '' : String(raw.value).trim();
		const currency = typeof raw.currency === 'string' ? raw.currency : '';
		if (amount === '' && currency === '') return undefined;
		return { value: NUMERIC.test(amount) ? Number(amount) : Number.NaN, currency };
	}
	if (kind === 'boolean') {
		if (raw === true || raw === 'true') return true;
		if (raw === false || raw === 'false') return false;
		return undefined;
	}
	return typeof raw === 'string' ? raw : String(raw);
}

/** Convert stored operands back into widget-friendly values. */
export function toWidget(kind: string, operand: unknown): unknown {
	if (kind === 'money') {
		if (!isRec(operand)) return {};
		return {
			value:
				typeof operand.value === 'number' && Number.isFinite(operand.value)
					? String(operand.value)
					: '',
			currency: typeof operand.currency === 'string' ? operand.currency : ''
		};
	}
	if (typeof operand === 'number') return Number.isFinite(operand) ? String(operand) : '';
	if (typeof operand === 'string') return operand;
	if (typeof operand === 'boolean') return String(operand);
	return '';
}

const RELATIVE = /^[+-]?\d{1,3}[dwmy]$/;
const ISO_DATE = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;
const PARTIAL_DATE = /^\d{4}(-\d{2}(-\d{2})?)?$/;

export type RelativeUnit = 'd' | 'w' | 'm' | 'y';
/** A unit with its direction: `-d` is "days ago", `+d` is "days from now". */
export type RelativeMode = `${'-' | '+'}${RelativeUnit}`;

const UNIT_WORDS: Record<RelativeUnit, string> = { d: 'days', w: 'weeks', m: 'months', y: 'years' };

export const RELATIVE_MODES: { value: RelativeMode; label: string }[] = [
	...(['d', 'w', 'm', 'y'] as const).map((u) => ({
		value: `-${u}` as RelativeMode,
		label: `${UNIT_WORDS[u]} ago`
	})),
	...(['d', 'w', 'm', 'y'] as const).map((u) => ({
		value: `+${u}` as RelativeMode,
		label: `${UNIT_WORDS[u]} from now`
	}))
];

/**
 * The parts of a `{rel}` draft for the "N units ago / from now" inputs. No sign, or `+`, is a
 * future offset, as on the server.
 */
export function relativeParts(operand: unknown): { count: string; mode: RelativeMode } {
	const rel = isRel(operand) ? operand.rel : '';
	const match = /^([+-]?)(.*?)([dwmy])?$/.exec(rel);
	const unit = (match?.[3] as RelativeUnit | undefined) ?? 'd';
	const sign = match?.[1] === '-' || rel === '' ? '-' : '+';
	return { count: match?.[2] ?? '', mode: `${sign}${unit}` };
}

export function relative(count: string, mode: RelativeMode): { rel: string } {
	return { rel: `${mode[0]}${count.trim()}${mode[1]}` };
}

function isValidDate(value: string): boolean {
	if (!ISO_DATE.test(value)) return false;
	return !Number.isNaN(new Date(`${value}T00:00:00Z`).getTime());
}

const MISSING: Record<string, string> = {
	rating: 'Choose a number of stars.',
	choice: 'Choose a value.',
	multichoice: 'Choose a value.',
	date: 'Choose a date.',
	boolean: 'Choose yes or no.'
};

/** Why one operand does not fit a field kind, or null when it does. */
export function operandProblem(kind: string, operand: unknown): string | null {
	if (operand === undefined || operand === null || operand === '')
		return MISSING[kind] ?? 'Enter a value.';
	if (isRef(operand)) return operand.ref ? null : 'Choose a field to compare with.';
	if (isRel(operand)) {
		if (kind !== 'date' && kind !== 'partialdate') return 'Enter a value.';
		return RELATIVE.test(operand.rel)
			? null
			: 'Enter a whole number of days, weeks, months or years (up to 999).';
	}
	switch (kind) {
		case 'number':
			return typeof operand === 'number' && Number.isFinite(operand) ? null : 'Enter a number.';
		case 'duration':
			return typeof operand === 'number' && Number.isFinite(operand) && operand >= 0
				? null
				: 'Enter a duration such as 45:00, 1:30:00 or 1h 30m.';
		case 'rating':
			return typeof operand === 'number' && Number.isFinite(operand)
				? null
				: 'Choose a number of stars.';
		case 'money':
			return isRec(operand) &&
				typeof operand.value === 'number' &&
				Number.isFinite(operand.value) &&
				typeof operand.currency === 'string' &&
				operand.currency !== ''
				? null
				: 'Enter an amount and a currency.';
		case 'date':
			return typeof operand === 'string' && isValidDate(operand) ? null : 'Choose a date.';
		case 'partialdate':
			return typeof operand === 'string' && PARTIAL_DATE.test(operand)
				? null
				: 'Enter a year, a year and month, or a full date: 1973, 1973-03 or 1973-03-14.';
		case 'boolean':
			return typeof operand === 'boolean' ? null : 'Choose yes or no.';
		default:
			return typeof operand === 'string' ? null : 'Enter a value.';
	}
}

function valueProblem(kind: string, op: string, value: unknown): string | null {
	const shape = valueShape(kind, op);
	if (shape === 'none') return null;
	if (shape === 'range') {
		if (!Array.isArray(value) || value.length !== 2) return 'Enter both ends of the range.';
		return operandProblem(kind, value[0]) ?? operandProblem(kind, value[1]);
	}
	if (shape === 'multi' || shape === 'list') {
		const list = Array.isArray(value) ? value : value === undefined ? [] : [value];
		if (list.length === 0) return kind === 'text' ? 'Enter a value.' : 'Choose at least one value.';
		for (const item of list) {
			const problem = operandProblem(kind === 'multichoice' ? 'choice' : kind, item);
			if (problem) return problem;
		}
		return null;
	}
	if (Array.isArray(value)) return 'Enter a single value.';
	return operandProblem(kind, value);
}

const EMPTY_WORDS = 'Enter some words to look for.';

/** Why a row cannot be sent yet, or null when it is ready. Never throws. */
export function conditionProblem(c: Condition, catalogue: Catalogue): string | null {
	try {
		switch (c.kind) {
			case 'text': {
				const q = typeof c.q === 'string' ? c.q.trim() : '';
				if (!q) return EMPTY_WORDS;
				return [...q].length > MAX_TEXT_LENGTH ? 'Use 200 characters or fewer.' : null;
			}
			case 'description':
			case 'name': {
				if (!operatorTakesValue(c.op)) return null;
				const words = typeof c.value === 'string' ? c.value.trim() : '';
				if (!words) return c.kind === 'name' && c.op === '=' ? 'Enter a name.' : EMPTY_WORDS;
				return [...words].length > MAX_TEXT_LENGTH ? 'Use 200 characters or fewer.' : null;
			}
			case 'media':
				return null;
			case 'collection': {
				const count = Array.isArray(c.in) ? c.in.length : 0;
				if (count === 0) return 'Choose at least one collection.';
				return count > MAX_COLLECTION_IDS
					? `Choose ${MAX_COLLECTION_IDS} collections or fewer.`
					: null;
			}
			case 'type':
				return Array.isArray(c.in) && c.in.length > 0 ? null : 'Choose at least one type.';
			case 'tag':
				return Array.isArray(c.tags) && c.tags.length > 0 ? null : 'Add at least one tag.';
			case 'favourite':
				return typeof c.value === 'boolean' ? null : 'Choose yes or no.';
			case 'date':
				return valueProblem('date', c.op, c.value);
			case 'field': {
				if (isBlank(c)) return 'Choose what to filter on.';
				const field = fieldOf(c, catalogue);
				// A field that no longer exists is left for the server to report.
				if (!field) return null;
				if (!operatorsForKind(field.kind).includes(c.op)) return 'Choose how to compare.';
				return valueProblem(field.kind, c.op, c.value);
			}
			default:
				return 'Choose what to filter on.';
		}
	} catch {
		return 'Choose what to filter on.';
	}
}

export type AppliedDraft = {
	query: Query;
	/** Draft path key to the same row's path key in `query`. */
	toApplied: Map<string, string>;
};

/** The draft without unfinished rows, and where each kept row ended up. */
export function applyDraft(draft: Query, catalogue: Catalogue): AppliedDraft {
	const toApplied = new Map<string, string>();
	const walk = (group: Group, from: Path, to: Path): Group | null => {
		const children: Node[] = [];
		group.children.forEach((child, i) => {
			const path = [...from, i];
			const target = [...to, children.length];
			if (isGroup(child)) {
				const kept = walk(child, path, target);
				if (kept) {
					toApplied.set(pathKey(path), pathKey(target));
					children.push(kept);
				}
			} else if (conditionProblem(child, catalogue) === null) {
				toApplied.set(pathKey(path), pathKey(target));
				children.push(child);
			}
		});
		if (children.length === 0) return null;
		if (group.op === 'not' && children.length !== 1) return null;
		return { op: group.op, children };
	};
	const where = draft.where ? walk(draft.where, [], []) : null;
	return { query: { ...draft, where }, toApplied };
}

/** Invert `toApplied`: an applied path key to its draft path. */
export function draftPathFor(toApplied: Map<string, string>, appliedKey: string): Path | null {
	for (const [draftKey, key] of toApplied)
		if (key === appliedKey) return draftKey === '' ? [] : draftKey.split('.').map(Number);
	return null;
}

/** 1-based condition numbers in reading order, keyed by path. */
export function conditionNumbers(query: Query): Map<string, number> {
	const numbers = new Map<string, number>();
	const walk = (group: Group, path: Path) =>
		group.children.forEach((child, i) => {
			const at = [...path, i];
			if (isGroup(child)) walk(child, at);
			else numbers.set(pathKey(at), numbers.size + 1);
		});
	if (query.where) walk(query.where, []);
	return numbers;
}

export function firstConditionPath(node: Node, path: Path): Path {
	if (!isGroup(node) || node.children.length === 0) return path;
	return firstConditionPath(node.children[0], [...path, 0]);
}

export type Chip = {
	key: string;
	path: Path;
	/** Path of the row to show when the chip is opened. */
	focus: Path;
	text: string;
	warning: boolean;
	/** What to say about the warning; null when the chip has none. */
	message: string | null;
};

const GROUP_WORDS = { and: 'All of', or: 'Any of', not: 'Not' } as const;

function conditionsIn(node: Node, path: Path): { condition: Condition; path: Path }[] {
	if (!isGroup(node)) return [{ condition: node, path }];
	return node.children.flatMap((child, i) => conditionsIn(child, [...path, i]));
}

/** One chip per top-level row of the filter; a nested group becomes one chip. */
export function chipModels(
	query: Query,
	lookup: SummaryLookup,
	warned: ReadonlySet<string> = new Set()
): { lead: string | null; chips: Chip[] } {
	const root = query.where;
	if (!root) return { lead: null, chips: [] };
	const chips = root.children.map((child, i): Chip => {
		const path = [i];
		const inside = conditionsIn(child, path);
		const flagged = inside.find((c) => warned.has(pathKey(c.path)));
		const warning = flagged !== undefined;
		const texts = inside.map((c) => describeCondition(c.condition, lookup));
		const text = isGroup(child)
			? `${GROUP_WORDS[child.op] ?? 'Any of'}: ${texts.join('; ')}`
			: texts[0];
		return {
			key: pathKey(path),
			path,
			focus: firstConditionPath(child, path),
			text,
			warning,
			message: flagged ? missingFieldMessage(flagged.condition) : null
		};
	});
	const lead =
		root.op === 'or' && chips.length > 1
			? 'Any of these:'
			: root.op === 'not'
				? 'None of these:'
				: null;
	return { lead, chips };
}

export type SortChoice = { value: string; label: string };

export function sortValue(sort: SortKey[]): string {
	const first = sort[0];
	if (!first) return 'default';
	if (first.by === 'field') return fieldSubject(first.type ?? '', first.key ?? '');
	return first.by;
}

export function sortFromValue(value: string, dir: 'asc' | 'desc'): SortKey[] {
	if (value === 'name' || value === 'created' || value === 'updated') return [{ by: value, dir }];
	const field = parseFieldSubject(value);
	if (field) return [{ by: 'field', type: field.type, key: field.key, dir }];
	return [];
}

export function isDateCondition(c: Condition): c is DateCondition {
	return c.kind === 'date';
}

/** What the builder's rows and groups need from the panel. */
export type BuilderView = {
	catalogue: Catalogue;
	/** Condition numbers by draft path key. */
	numbers: Map<string, number>;
	/** Draft path keys of rows the server could not match. */
	warned: ReadonlySet<string>;
	/** Draft path key of the row a server error names, and its message. */
	error: { key: string; message: string } | null;
	/** Every collection the person has (null while loading or if it could not be read). */
	collections: readonly { id: string; name: string }[] | null;
	/** The collection being edited; it cannot be picked (it cannot refer to itself). */
	excludeCollectionId: string | null;
	/** Reading the collections failed; `retryCollections` reads them again. */
	collectionsFailed: boolean;
	retryCollections(): void;
	canAddCondition: boolean;
	canAddGroup(groupPath: Path): boolean;
	update(path: Path, condition: Condition, options?: { debounce?: boolean }): void;
	remove(path: Path): void;
	addCondition(groupPath: Path): void;
	addGroup(groupPath: Path): void;
	setGroupOp(path: Path, op: 'and' | 'or'): void;
};

const PICKED_KINDS = new Set(['choice', 'multichoice', 'rating', 'date', 'boolean']);

/** Typed values wait for a pause before reaching the URL; picked ones apply at once. */
export function isTypedKind(kind: string): boolean {
	return !PICKED_KINDS.has(kind);
}

/** The options a choice or multiple-choice field offers (a linked list's are filled in on read). */
export function fieldOptions(field: FieldInfo | undefined): string[] {
	const prop: unknown = field?.prop;
	if (!isRec(prop)) return [];
	const items = isRec(prop.items) ? prop.items.enum : undefined;
	const list = Array.isArray(prop.enum) ? prop.enum : Array.isArray(items) ? items : [];
	return list.filter((o): o is string => typeof o === 'string');
}

/** Strings in a stored list value; anything else is dropped for display. */
export function stringList(value: unknown): string[] {
	const list = Array.isArray(value) ? value : value === undefined ? [] : [value];
	return list.filter((v): v is string => typeof v === 'string');
}

export const STALE_FIELD_MESSAGE = 'This field no longer exists, so nothing matches.';
export const STALE_COLLECTION_MESSAGE =
	'A collection here no longer exists, so it matches nothing.';
export const NO_ITEM_FIELD_MESSAGE = 'No item has this field.';
/** The same wording, lower-cased for the field picker's trigger. */
export const NO_ITEM_FIELD_NOTE = 'no item has this field';

/** What to say about a field row that cannot be matched. */
export function missingFieldMessage(c: Condition): string {
	if (c.kind === 'collection') return STALE_COLLECTION_MESSAGE;
	return c.kind === 'field' && c.field_kind !== undefined
		? NO_ITEM_FIELD_MESSAGE
		: STALE_FIELD_MESSAGE;
}

/** The group at `path`, or null when the path does not lead to one. */
export function groupAt(query: Query, path: Path): Group | null {
	let node: Node | undefined = query.where ?? undefined;
	for (const index of path) node = node && isGroup(node) ? node.children[index] : undefined;
	return node && isGroup(node) ? node : null;
}

/** A stable key for comparing queries, whatever order their members were written in. */
export function queryKey(query: Query): string {
	return JSON.stringify(decodeQuery(encodeQuery(query)) ?? query);
}
export const STALE_SORT_MESSAGE = 'This field no longer exists, so it is not used for sorting.';

/** The server's reason for refusing a filter, and the filter path it names (if any). */
export type BuilderError = { message: string; path: Path | null };

const HIDDEN_BY_WIDGET = new Set(['number', 'rating', 'date', 'boolean', 'money']);

/**
 * A stored value the field's widget cannot display (text in a number field, say), so the row
 * can still show what is there. Null when the widget shows the value itself.
 */
export function strayValueText(kind: string, value: unknown): string | null {
	if (!HIDDEN_BY_WIDGET.has(kind) || value === undefined || value === '') return null;
	if (typeof value === 'string') return kind === 'date' && ISO_DATE.test(value) ? null : value;
	if (typeof value === 'number' || typeof value === 'boolean')
		return operandProblem(kind, value) ? String(value) : null;
	return null;
}

export const ARCHIVED_FIELD_MESSAGE = 'This field is archived, so nothing matches.';

export type FieldStatus = 'ok' | 'loading' | 'missing' | 'archived';

/**
 * Whether a field row's field can be offered: still loading the item types, gone, archived,
 * or fine. Rows about anything other than a field are always fine.
 */
export function fieldStatus(c: Condition, catalogue: Catalogue): FieldStatus {
	if (c.kind !== 'field' || isBlank(c)) return 'ok';
	if (!catalogue.loaded) return 'loading';
	if (c.field_kind !== undefined) {
		// An unread listing, or one cut off at the server's cap, says nothing either way.
		const listed =
			catalogue.itemFields === null ||
			catalogue.itemFields.length >= ITEM_FIELDS_CAP ||
			findItemField(catalogue, c.field_kind, c.key);
		return listed ? 'ok' : 'missing';
	}
	const field = fieldOf(c, catalogue);
	if (!field) return 'missing';
	return field.archived ? 'archived' : 'ok';
}

/** The "Per-item fields" options for the field picker; searchable by group name and label. */
export function itemFieldPickerItems(catalogue: Catalogue): ComboboxItem[] {
	const group = itemFieldGroup(catalogue);
	if (!group) return [];
	return group.options.map((o) => ({
		value: o.value,
		label: o.label,
		group: group.label,
		selectedLabel: `${group.label} › ${o.label}`
	}));
}

/** Path keys of per-item rows whose field no item has; the server does not flag these. */
export function missingItemFieldPaths(query: Query, catalogue: Catalogue): Set<string> {
	const out = new Set<string>();
	if (!query.where) return out;
	for (const { condition, path } of conditionsIn(query.where, [])) {
		if (
			condition.kind === 'field' &&
			condition.field_kind !== undefined &&
			fieldStatus(condition, catalogue) === 'missing'
		)
			out.add(pathKey(path));
	}
	return out;
}

export const DELETED_COLLECTION_LABEL = 'Deleted collection';

/** The name of a collection a row names, or a stand-in when it is gone or still loading. */
export function collectionLabel(
	collections: readonly { id: string; name: string }[] | null,
	id: string
): string {
	if (collections === null) return 'Collection';
	return collections.find((c) => c.id === id)?.name ?? DELETED_COLLECTION_LABEL;
}
