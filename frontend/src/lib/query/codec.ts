import {
	MAX_CONDITIONS,
	MAX_DEPTH,
	MAX_LIST_LENGTH,
	MAX_SORT_KEYS,
	MAX_TEXT_LENGTH,
	type Condition,
	type Group,
	type Node,
	type Operand,
	type Query,
	type SortKey,
	type Value
} from './types';

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

function str(value: unknown): string | null {
	return typeof value === 'string' && value.length <= MAX_TEXT_LENGTH ? value : null;
}

function strList(value: unknown): string[] | null {
	if (!Array.isArray(value) || value.length > MAX_LIST_LENGTH) return null;
	const out: string[] = [];
	for (const item of value) {
		const s = str(item);
		if (s === null) return null;
		out.push(s);
	}
	return out;
}

function operand(value: unknown): Operand | null {
	if (typeof value === 'boolean' || typeof value === 'number') return value;
	if (typeof value === 'string') return str(value);
	if (!isRec(value)) return null;
	const keys = Object.keys(value).sort().join(',');
	if (keys === 'rel') {
		const rel = str(value.rel);
		return rel === null ? null : { rel };
	}
	if (keys === 'ref') {
		const ref = str(value.ref);
		return ref === null ? null : { ref };
	}
	if (keys === 'currency,value' && typeof value.value === 'number') {
		const currency = str(value.currency);
		return currency === null ? null : { value: value.value, currency };
	}
	return null;
}

function operandValue(value: unknown): Value | null {
	if (!Array.isArray(value)) return operand(value);
	if (value.length > MAX_LIST_LENGTH) return null;
	const out: Operand[] = [];
	for (const item of value) {
		const o = operand(item);
		if (o === null) return null;
		out.push(o);
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
			const op = str(data.op);
			const value = operandValue(data.value);
			const on = data.on;
			if (op === null || value === null || (on !== 'created' && on !== 'updated')) return null;
			return { kind: 'date', on, op, value };
		}
		case 'field': {
			const type = str(data.type);
			const key = str(data.key);
			const op = str(data.op);
			if (type === null || key === null || op === null) return null;
			const out: Condition = { kind: 'field', type, key, op };
			if (data.sub_key !== undefined) {
				const sub = str(data.sub_key);
				if (sub === null) return null;
				out.sub_key = sub;
			}
			if (data.value !== undefined) {
				const value = operandValue(data.value);
				if (value === null) return null;
				out.value = value;
			}
			return out;
		}
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
function group(data: unknown, depth: number, budget: { conditions: number }): Group | null {
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
			child = condition(item);
		} else {
			child = group(item, depth + 1, budget);
		}
		if (child === null) return null;
		children.push(child);
	}
	return { op, children };
}

/** Parse a query from the URL, or null when it is not a well-formed one. Never throws. */
export function decodeQuery(token: string): Query | null {
	try {
		const data: unknown = JSON.parse(fromBase64Url(token));
		if (!isRec(data) || data.v !== 1 || !Array.isArray(data.sort)) return null;
		if (data.sort.length > MAX_SORT_KEYS) return null;
		const sort: SortKey[] = [];
		for (const item of data.sort) {
			const key = sortKey(item);
			if (key === null) return null;
			sort.push(key);
		}
		if (data.where === null) return { v: 1, where: null, sort };
		const where = group(data.where, 1, { conditions: 0 });
		return where === null ? null : { v: 1, where, sort };
	} catch {
		return null;
	}
}
