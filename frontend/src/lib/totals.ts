import type { NodeMeasureRequest, NodeMeasureResponse } from '$lib/api/client';
import { readPropMeta } from '$lib/prop-meta';
import { formatFieldValue, type Catalogue, type FieldInfo } from '$lib/query/fields';
import type { Query } from '$lib/query/types';

/**
 * Totals shown above a collection's items: sums, averages and extremes of its fields, worked out
 * by `POST /nodes/aggregate`. This file is the pure part: which totals to show when the person
 * has not chosen (money summed, numbers averaged), the words for each, and how a result reads.
 */

export type TotalFunction = 'sum' | 'avg' | 'min' | 'max';

/** The most totals a collection shows (the server accepts ten). */
export const MAX_TOTALS = 10;
/** What the automatic totals pick: money fields to add up, number fields to average. */
export const AUTO_MONEY = 3;
export const AUTO_NUMBERS = 2;

const ADDABLE: readonly TotalFunction[] = ['sum', 'avg', 'min', 'max'];
const FUNCTIONS_BY_KIND: Readonly<Record<string, readonly TotalFunction[]>> = {
	money: ADDABLE,
	number: ADDABLE,
	duration: ADDABLE,
	rating: ADDABLE,
	date: ['min', 'max'],
	partialdate: ['min', 'max']
};

const DATE_KINDS = new Set(['date', 'partialdate']);

/** The functions a total of this kind of field can take; none when it cannot be totalled. */
export function functionsFor(kind: string): readonly TotalFunction[] {
	return FUNCTIONS_BY_KIND[kind] ?? [];
}

/** "Total", "Average", "Lowest", "Highest"; "Earliest" and "Latest" for a date. */
export function functionLabel(fn: string, kind: string | null): string {
	const date = kind !== null && DATE_KINDS.has(kind);
	switch (fn) {
		case 'sum':
			return 'Total';
		case 'avg':
			return 'Average';
		case 'min':
			return date ? 'Earliest' : 'Lowest';
		case 'max':
			return date ? 'Latest' : 'Highest';
		default:
			return fn;
	}
}

/** A measure the server can run: a function over one type's field or a saved field. */
export type Total = NodeMeasureRequest;

/** The same measure, however its keys were written. */
export function totalKey(total: Total): string {
	return JSON.stringify([total.fn, total.type ?? null, total.key ?? null, total.origin ?? null]);
}

/** The condition tree of everything on a collection, manual or smart. */
export function collectionTotalsQuery(collectionId: string): Query {
	return {
		v: 1,
		where: {
			op: 'and',
			children: [{ kind: 'collection', mode: 'any', in: [collectionId] }]
		}
	} as Query;
}

/** The fields a type holds itself: not an archived one, a column, or one its parent also has. */
function ownFields(catalogue: Catalogue): FieldInfo[] {
	const parents = new Map(catalogue.types.map((t) => [t.slug, t.parent ?? null]));
	const keysOf = new Map<string, Set<string>>();
	for (const field of catalogue.fields) {
		if (field.subKey !== undefined || field.archived) continue;
		const keys = keysOf.get(field.type) ?? new Set<string>();
		keys.add(field.key);
		keysOf.set(field.type, keys);
	}
	return catalogue.fields.filter((field) => {
		if (field.subKey !== undefined || field.archived) return false;
		const parent = parents.get(field.type);
		return !(parent && keysOf.get(parent)?.has(field.key));
	});
}

function originOf(field: FieldInfo): string | null {
	const origin = readPropMeta(field.prop).origin;
	if (typeof origin !== 'object' || origin === null) return null;
	const preset = (origin as { preset?: unknown }).preset;
	return typeof preset === 'string' ? preset : null;
}

/** The measure that reads a field: its saved field when it has one, so every type is covered. */
function readField(field: FieldInfo, fn: TotalFunction): Total {
	const origin = originOf(field);
	return origin ? { fn, origin } : { fn, type: field.type, key: field.key };
}

/**
 * The totals to show when the person has not chosen: up to three money fields added up and two
 * number fields averaged, from the item types in the collection (a type counts when it or one
 * of its subtypes has items). An empty collection, or one with nothing to total, shows none.
 */
export function automaticTotals(catalogue: Catalogue, typeSlugs: readonly string[]): Total[] {
	const present = new Set(typeSlugs);
	for (const t of catalogue.types) {
		if (t.parent && present.has(t.slug)) present.add(t.parent);
	}
	const picked: Total[] = [];
	const seen = new Set<string>();
	const take = (kind: string, fn: TotalFunction, limit: number) => {
		let taken = 0;
		for (const field of ownFields(catalogue)) {
			if (taken >= limit) return;
			if (field.kind !== kind || !present.has(field.type)) continue;
			const total = readField(field, fn);
			if (seen.has(totalKey(total))) continue;
			seen.add(totalKey(total));
			picked.push(total);
			taken += 1;
		}
	};
	take('money', 'sum', AUTO_MONEY);
	take('number', 'avg', AUTO_NUMBERS);
	return picked;
}

/** The totals to show: the person's own when they have chosen, otherwise the automatic ones. */
export function shownTotals(chosen: Total[] | null | undefined, automatic: Total[]): Total[] {
	return chosen ?? automatic;
}

export type TotalChoice = {
	/** `type/key`, or `origin:id`: what the field menu selects. */
	value: string;
	label: string;
	kind: string;
	field: Pick<Total, 'type' | 'key' | 'origin'>;
};

/** The fields a total can be taken of, labelled "Price (Film)", for the Add a total menu. */
export function totalChoices(catalogue: Catalogue): TotalChoice[] {
	const choices: TotalChoice[] = [];
	for (const field of ownFields(catalogue)) {
		if (functionsFor(field.kind).length === 0) continue;
		choices.push({
			value: `${field.type}/${field.key}`,
			label: `${field.label} (${field.typeLabel})`,
			kind: field.kind,
			field: { type: field.type, key: field.key }
		});
	}
	return choices.sort((a, b) => a.label.localeCompare(b.label, 'en-GB'));
}

function fieldFor(catalogue: Catalogue, total: Total): FieldInfo | undefined {
	if (total.origin) return catalogue.fields.find((f) => originOf(f) === total.origin);
	return catalogue.fields.find(
		(f) => f.subKey === undefined && f.type === total.type && f.key === total.key
	);
}

/** "Total price", "Average rating", or "Items"; the key when the field has gone. */
export function describeTotal(total: Total, catalogue: Catalogue): string {
	if (total.fn === 'count') return 'Items';
	const field = fieldFor(catalogue, total);
	const name = (field?.label ?? total.key ?? 'field').toLowerCase();
	return `${functionLabel(total.fn, field?.kind ?? null)} ${name}`;
}

const NUMBER = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 });

/** An amount in its own currency ("£1,204.50"); the code after the number when it is unknown. */
export function formatMoney(value: number, currency: string): string {
	try {
		return new Intl.NumberFormat('en-GB', { style: 'currency', currency }).format(value);
	} catch {
		return `${NUMBER.format(value)} ${currency}`;
	}
}

/** One shown value of a total. */
export type ShownValue = { text: string; currency?: string };

/**
 * How a result reads: one entry per currency for money, never converted or added together; a
 * single entry otherwise; and a dash for no value. Dates, ratings and durations read as the
 * cards show them.
 */
export function formatResult(
	result: Pick<NodeMeasureResponse, 'value' | 'currencies'>,
	field: FieldInfo | undefined
): ShownValue[] {
	if (result.currencies.length > 0) {
		return result.currencies.map((c) => ({
			text: formatMoney(c.value, c.currency),
			currency: c.currency
		}));
	}
	const value = result.value;
	if (value === null || value === undefined) return [{ text: '–' }];
	if (typeof value === 'string')
		return [{ text: field ? (formatFieldValue(field, value) ?? value) : value }];
	if (field && field.kind !== 'number') {
		const text = formatFieldValue(field, value);
		if (text !== null && field.kind !== 'rating') return [{ text }];
	}
	return [{ text: NUMBER.format(value) }];
}

/** The field a total reads, for formatting its result. */
export function totalField(total: Total, catalogue: Catalogue): FieldInfo | undefined {
	return fieldFor(catalogue, total);
}
