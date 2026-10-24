import {
	MAX_COLLECTION_IDS,
	MAX_CONDITIONS,
	MAX_DEPTH,
	MAX_LIST_LENGTH,
	MAX_SORT_KEYS,
	MAX_TEXT_LENGTH,
	type Condition,
	type ConnectionCondition,
	type Group,
	type Node,
	type Operand,
	type Query,
	type SortKey,
	type Value
} from './types';
import {
	LIST_OPERATORS,
	operatorsForCondition,
	operatorsForKind,
	operatorTakesValue
} from './operators';

function toBase64Url(text: string): string {
	let binary = '';
	for (const byte of new TextEncoder().encode(text)) binary += String.fromCharCode(byte);
	return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function fromBase64Url(token: string): string {
	if (!/^[A-Za-z0-9_-]+$/.test(token)) throw new Error('Not base64url');
	const base64 = token.replace(/-/g, '+').replace(/_/g, '/');
	const binary = atob(base64 + '='.repeat((4 - (base64.length % 4)) % 4));
	return new TextDecoder('utf-8', { fatal: true }).decode(
		Uint8Array.from(binary, (c) => c.charCodeAt(0))
	);
}

/** The query as a URL-safe string. The server validates; this is only transport. */
export function encodeQuery(query: Query): string {
	return toBase64Url(JSON.stringify(query));
}

type Rec = Record<string, unknown>;

function isRec(value: unknown): value is Rec {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Operators the server accepts structurally (backend graph/domain/query.py). */
const OPERATORS = new Set([
	'=',
	'!=',
	'~',
	'>',
	'>=',
	'<',
	'<=',
	'between',
	'in',
	'not_in',
	'empty',
	'not_empty',
	'has',
	'incomplete',
	'complete'
]);
const DATE_OPERATORS = new Set(['=', '>', '>=', '<', '<=', 'between']);
const BETWEEN_LENGTH = 2;
const RELATIVE = /^[+-]?\d{1,3}[dwmy]$/;

/** Length in characters, as Python counts it, not in UTF-16 units. */
function withinLength(value: string, min: number): boolean {
	// Characters never outnumber UTF-16 units, so long input is rejected without a scan.
	if (value.length > 2 * MAX_TEXT_LENGTH) return false;
	let count = 0;
	for (const _ of value) count++;
	return count >= min && count <= MAX_TEXT_LENGTH;
}

/** A required text: 1 to 200 characters. */
function str(value: unknown): string | null {
	return typeof value === 'string' && withinLength(value, 1) ? value : null;
}

function strList(value: unknown): string[] | null {
	if (!Array.isArray(value) || value.length < 1 || value.length > MAX_LIST_LENGTH) return null;
	const out: string[] = [];
	for (const item of value) {
		const s = str(item);
		if (s === null) return null;
		out.push(s);
	}
	return out;
}

/** `1e999` parses as Infinity, which JSON cannot send back. */
function isFiniteNumber(value: unknown): value is number {
	return typeof value === 'number' && Number.isFinite(value);
}

function operand(value: unknown): Operand | null {
	if (typeof value === 'boolean' || isFiniteNumber(value)) return value;
	// A literal string may be empty; only the upper bound applies.
	if (typeof value === 'string') return withinLength(value, 0) ? value : null;
	if (!isRec(value)) return null;
	const keys = Object.keys(value).sort().join(',');
	if (keys === 'rel') {
		return typeof value.rel === 'string' && RELATIVE.test(value.rel) ? { rel: value.rel } : null;
	}
	if (keys === 'ref') {
		const ref = str(value.ref);
		return ref === null ? null : { ref };
	}
	if (keys === 'currency,value' && isFiniteNumber(value.value)) {
		const currency = str(value.currency);
		return currency === null ? null : { value: value.value, currency };
	}
	return null;
}

function operands(value: unknown, min: number, max: number): Operand[] | null {
	if (!Array.isArray(value) || value.length < min || value.length > max) return null;
	const out: Operand[] = [];
	for (const item of value) {
		const o = operand(item);
		if (o === null) return null;
		out.push(o);
	}
	return out;
}

/**
 * The value a comparison needs, shaped by its operator. `undefined` means none
 * (a no-value operator); `null` means the data is malformed.
 */
function comparisonValue(op: string, data: Rec): Value | null | undefined {
	if (!operatorTakesValue(op)) return 'value' in data ? null : undefined;
	if (!('value' in data)) return null;
	const raw = data.value;
	if (op === 'between') return operands(raw, BETWEEN_LENGTH, BETWEEN_LENGTH);
	if (LIST_OPERATORS.has(op)) return operands(raw, 1, MAX_LIST_LENGTH);
	if (op === 'has' && Array.isArray(raw)) return operands(raw, 1, MAX_LIST_LENGTH);
	return operand(raw);
}

/** True when an operand, or any of a list, is a reference to another field. */
function hasReference(value: Value | undefined): boolean {
	const items = Array.isArray(value) ? value : [value];
	return items.some((item) => isRec(item) && 'ref' in item);
}

/** A field condition names an item type or a field kind, never both (as on the server). */
function fieldCondition(data: Rec): Condition | null {
	const key = str(data.key);
	const op = data.op;
	if (key === null || typeof op !== 'string' || !OPERATORS.has(op)) return null;
	// A null type or sub_key means none, as on the server.
	const hasType = data.type !== undefined && data.type !== null;
	const hasKind = data.field_kind !== undefined && data.field_kind !== null;
	if (hasType === hasKind) return null;
	const out: Extract<Condition, { kind: 'field' }> = { kind: 'field', key, op };
	if (hasType) {
		const type = str(data.type);
		if (type === null) return null;
		out.type = type;
	} else {
		const kind = str(data.field_kind);
		if (kind === null || operatorsForKind(kind).length === 0) return null;
		out.field_kind = kind;
	}
	if (data.sub_key !== undefined && data.sub_key !== null) {
		const sub = str(data.sub_key);
		if (sub === null || hasKind) return null;
		out.sub_key = sub;
	}
	const value = comparisonValue(op, data);
	if (value === null || (hasKind && hasReference(value))) return null;
	if (value !== undefined) out.value = value;
	return out;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function collectionIds(value: unknown): string[] | null {
	if (!Array.isArray(value) || value.length < 1 || value.length > MAX_COLLECTION_IDS) return null;
	return value.every((id) => typeof id === 'string' && UUID.test(id)) ? (value as string[]) : null;
}

/** Description (`~`, `empty`, `not_empty`) and name (`~`, `=`): a value exactly when one is needed. */
function textCondition(data: Rec): Condition | null {
	const kind = data.kind === 'name' ? 'name' : 'description';
	const op = data.op;
	if (typeof op !== 'string' || !operatorsForCondition(kind).includes(op)) return null;
	if (!operatorTakesValue(op)) {
		return 'value' in data ? null : ({ kind, op } as Condition);
	}
	const value = str(data.value);
	return value === null ? null : ({ kind, op, value } as Condition);
}

/**
 * A connection's far-end filter is parsed with its own depth, and may not hold another
 * connection (the server's rule). Its conditions share the budget of the whole query.
 */
function connectionCondition(data: Rec, budget: Budget, farEnd: boolean): Condition | null {
	if (farEnd) return null;
	const { mode } = data;
	if (mode !== 'exists' && mode !== 'none' && mode !== 'to') return null;
	const out: ConnectionCondition = { kind: 'connection', mode };
	if (data.direction !== undefined) {
		if (data.direction !== 'out' && data.direction !== 'in' && data.direction !== 'any')
			return null;
		out.direction = data.direction;
	}
	if (data.relationship !== undefined && data.relationship !== null) {
		const relationship = str(data.relationship);
		if (relationship === null) return null;
		out.relationship = relationship;
	}
	const hasWhere = data.where !== undefined && data.where !== null;
	if (mode === 'to') {
		if (hasWhere || typeof data.item !== 'string' || !UUID.test(data.item)) return null;
		out.item = data.item;
		return out;
	}
	if (data.item !== undefined && data.item !== null) return null;
	if (hasWhere) {
		const where = group(data.where, 1, budget, true);
		if (where === null) return null;
		out.where = where;
	}
	return out;
}

function condition(data: Rec): Condition | null {
	switch (data.kind) {
		case 'text': {
			const q = str(data.q);
			return q === null ? null : { kind: 'text', q };
		}
		case 'type': {
			const list = strList(data.in);
			return list === null ? null : { kind: 'type', in: list };
		}
		case 'favourite':
			return typeof data.value === 'boolean' ? { kind: 'favourite', value: data.value } : null;
		case 'tag': {
			const tags = strList(data.tags);
			const mode = data.mode;
			if (tags === null || (mode !== 'any' && mode !== 'all' && mode !== 'none')) return null;
			return { kind: 'tag', mode, tags };
		}
		case 'date': {
			const op = data.op;
			const on = data.on;
			if (typeof op !== 'string' || !DATE_OPERATORS.has(op)) return null;
			if (on !== 'created' && on !== 'updated') return null;
			const value = comparisonValue(op, data);
			return value === null || value === undefined ? null : { kind: 'date', on, op, value };
		}
		case 'description':
		case 'name':
			return textCondition(data);
		case 'media': {
			const { mode, type } = data;
			if (mode !== 'has' && mode !== 'none') return null;
			if (type === undefined) return { kind: 'media', mode };
			return type === 'image' || type === 'document' ? { kind: 'media', mode, type } : null;
		}
		case 'collection': {
			const { mode } = data;
			const ids = collectionIds(data.in);
			if ((mode !== 'any' && mode !== 'none') || ids === null) return null;
			return { kind: 'collection', mode, in: ids };
		}
		case 'field':
			return fieldCondition(data);
		default:
			return null;
	}
}

function sortKey(data: unknown): SortKey | null {
	if (!isRec(data)) return null;
	const by = data.by;
	if (by !== 'name' && by !== 'created' && by !== 'updated' && by !== 'field') return null;
	const out: SortKey = { by };
	if (data.dir !== undefined) {
		if (data.dir !== 'asc' && data.dir !== 'desc') return null;
		out.dir = data.dir;
	}
	if (by === 'field') {
		const type = str(data.type);
		const key = str(data.key);
		if (type === null || key === null) return null;
		out.type = type;
		out.key = key;
	}
	return out;
}

/**
 * Rebuilds a validated copy of a group, or returns null. Recursion is bounded
 * by MAX_DEPTH, which is checked before descending, so hostile input is safe.
 */
type Budget = { conditions: number };

function group(data: unknown, depth: number, budget: Budget, farEnd = false): Group | null {
	if (depth > MAX_DEPTH || !isRec(data)) return null;
	const op = data.op;
	if (op !== 'and' && op !== 'or' && op !== 'not') return null;
	const raw = data.children;
	if (!Array.isArray(raw) || raw.length === 0 || (op === 'not' && raw.length !== 1)) return null;
	const children: Node[] = [];
	for (const item of raw) {
		if (!isRec(item)) return null;
		let child: Node | null;
		if ('kind' in item) {
			if (++budget.conditions > MAX_CONDITIONS) return null;
			child =
				item.kind === 'connection' ? connectionCondition(item, budget, farEnd) : condition(item);
		} else {
			child = group(item, depth + 1, budget, farEnd);
		}
		if (child === null) return null;
		children.push(child);
	}
	return { op, children };
}

/** Validate an already-parsed query (such as a saved definition), or null. Never throws. */
export function parseQuery(data: unknown): Query | null {
	try {
		if (!isRec(data) || data.v !== 1) return null;
		// A missing sort means creation order.
		const rawSort = data.sort === undefined ? [] : data.sort;
		if (!Array.isArray(rawSort) || rawSort.length > MAX_SORT_KEYS) return null;
		const sort: SortKey[] = [];
		for (const item of rawSort) {
			const key = sortKey(item);
			if (key === null) return null;
			sort.push(key);
		}
		if (data.where === null || data.where === undefined) return { v: 1, where: null, sort };
		const where = group(data.where, 1, { conditions: 0 });
		return where === null ? null : { v: 1, where, sort };
	} catch {
		return null;
	}
}

/** Parse a query from the URL, or null when it is not a well-formed one. Never throws. */
export function decodeQuery(token: string): Query | null {
	try {
		return parseQuery(JSON.parse(fromBase64Url(token)));
	} catch {
		return null;
	}
}
