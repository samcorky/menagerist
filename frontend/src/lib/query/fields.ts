import { coreForProp, getDescriptor } from '$lib/field-types';
import { readPropMeta, withPropMeta } from '$lib/schema-meta';
import type { JsonSchemaProperty } from '$lib/schema-types';
import type { ItemField } from '$lib/item-fields';
import { operatorsForKind } from './operators';
import type { SummaryLookup } from './summary';

/** Kinds whose conditions may compare with another field (backend REF_KINDS). */
export const REF_KINDS: ReadonlySet<string> = new Set([
	'number',
	'duration',
	'rating',
	'money',
	'date'
]);

/** Kinds the server can sort on (backend SORTABLE_KINDS). */
export const SORTABLE_KINDS: ReadonlySet<string> = new Set([
	'text',
	'url',
	'email',
	'phone',
	'number',
	'duration',
	'rating',
	'money',
	'date',
	'partialdate',
	'choice'
]);

export type FieldInfo = {
	type: string;
	typeLabel: string;
	key: string;
	/** A table (group) column. */
	subKey?: string;
	/** "Rating", or "Cast › Role" for a table column. */
	label: string;
	kind: string;
	prop: JsonSchemaProperty;
	archived: boolean;
	/** The saved field a "Saved fields" entry stands for. */
	origin?: string;
	/** A choice with no option list to offer, so its values are typed (R17). */
	typedChoice?: boolean;
};

/** A saved single field the builder can search by, from the presets listing. */
export type SavedField = { id: string; label: string; property: JsonSchemaProperty };

export type ItemTypeLike = {
	slug: string;
	label: string;
	attributes_schema?: Record<string, unknown> | null;
};

export type Catalogue = {
	types: { slug: string; label: string }[];
	fields: FieldInfo[];
	/** False until the item types have loaded; rows must not be called stale before then. */
	loaded: boolean;
	/** The per-item fields in use; null until read, or when the read failed. */
	itemFields: readonly ItemField[] | null;
	/** The person's saved single fields; null until read, or when the read failed. */
	savedFields: readonly SavedField[] | null;
};

/** The most rows the server returns; a listing this long may be missing fields. */
export const ITEM_FIELDS_CAP = 200;

/** The most saved fields read for the picker; a listing this long may be missing some. */
export const SAVED_FIELDS_CAP = 100;

/** The field picker's heading for a field by key and kind on any item, of any type. */
export const ITEM_FIELDS_LABEL = 'Any item type';

/** The field picker's heading for fields copied from a saved field. */
export const SAVED_FIELDS_LABEL = 'Saved fields';

function isRec(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function kindOf(prop: JsonSchemaProperty): string | null {
	try {
		return coreForProp(prop)?.kind ?? null;
	} catch {
		return null;
	}
}

function propertiesOf(schema: unknown): [string, JsonSchemaProperty][] {
	const props = isRec(schema) ? schema.properties : undefined;
	if (!isRec(props)) return [];
	return Object.entries(props).filter((e): e is [string, JsonSchemaProperty] => isRec(e[1]));
}

function title(prop: JsonSchemaProperty, key: string): string {
	return typeof prop.title === 'string' && prop.title.trim() ? prop.title : key;
}

/** Every field of every item type, archived ones included (for labelling old conditions). */
export function buildCatalogue(
	itemTypes: readonly ItemTypeLike[],
	loaded = true,
	itemFields: readonly ItemField[] | null = null,
	savedFields: readonly SavedField[] | null = null
): Catalogue {
	const fields: FieldInfo[] = [];
	for (const t of itemTypes) {
		for (const [key, prop] of propertiesOf(t.attributes_schema)) {
			const kind = kindOf(prop);
			if (!kind) continue;
			const label = title(prop, key);
			const archived = readPropMeta(prop).archived === true;
			const base = { type: t.slug, typeLabel: t.label, key, prop, archived };
			fields.push({ ...base, label, kind });
			if (kind !== 'group' || prop.type !== 'array' || !isRec(prop.items)) continue;
			for (const [subKey, sub] of propertiesOf(prop.items)) {
				const subKind = kindOf(sub);
				if (!subKind) continue;
				fields.push({
					...base,
					subKey,
					label: `${label} › ${title(sub, subKey)}`,
					kind: subKind,
					prop: sub,
					archived: archived || readPropMeta(sub).archived === true
				});
			}
		}
	}
	return {
		types: itemTypes.map((t) => ({ slug: t.slug, label: t.label })),
		fields,
		loaded,
		itemFields,
		savedFields
	};
}

export function typeLabel(catalogue: Catalogue, slug: string): string {
	return catalogue.types.find((t) => t.slug === slug)?.label ?? slug;
}

/** "Film › Rating" for a field reference, from the catalogue when it is known. */
export function fieldReferenceLabel(
	catalogue: Catalogue,
	type: string | undefined,
	key: string,
	subKey?: string
): string {
	const field = type === undefined ? undefined : findField(catalogue, type, key, subKey);
	const name = field?.label ?? (subKey ? `${key} › ${subKey}` : key);
	return `${type === undefined ? ITEM_FIELDS_LABEL : typeLabel(catalogue, type)} › ${name}`;
}

type AnyField = ItemField & { prop?: JsonSchemaProperty };

const anyFieldCache = new WeakMap<Catalogue, AnyField[]>();

/**
 * Fields worth searching by key and kind on any item: a top-level field on two or more item
 * types, or one individual items carry. One row per key and kind, labelled by the most
 * common title and sorted by it. A field on one type only is left to that type's group.
 * `prop` is the first type field's property, so its option list can be offered.
 */
export function anyTypeFields(catalogue: Catalogue): AnyField[] {
	const cached = anyFieldCache.get(catalogue);
	if (cached) return cached;
	const rows = new Map<
		string,
		{ row: AnyField; titles: Map<string, number>; types: Set<string>; own: boolean }
	>();
	const add = (
		key: string,
		kind: string,
		label: string,
		count: number,
		type?: string,
		prop?: JsonSchemaProperty
	) => {
		const id = `${kind}:${key}`;
		const entry = rows.get(id) ?? {
			row: { key, kind, label, count: 0, prop },
			titles: new Map<string, number>(),
			types: new Set<string>(),
			own: false
		};
		if (type === undefined) entry.own = true;
		else entry.types.add(type);
		entry.row.count += count;
		entry.row.prop ??= prop;
		entry.titles.set(label, (entry.titles.get(label) ?? 0) + Math.max(count, 1));
		rows.set(id, entry);
	};
	for (const f of catalogue.fields) {
		if (f.subKey || f.archived || operatorsForKind(f.kind).length === 0) continue;
		add(f.key, f.kind, f.label, 0, f.type, f.prop);
	}
	for (const f of catalogue.itemFields ?? []) add(f.key, f.kind, f.label, f.count);
	const reachable = [...rows.values()].filter((e) => e.own || e.types.size > 1);
	const out = reachable.map(({ row, titles }) => {
		const [label] = [...titles].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0];
		return { ...row, label };
	});
	out.sort((a, b) => a.label.localeCompare(b.label) || a.kind.localeCompare(b.kind));
	anyFieldCache.set(catalogue, out);
	return out;
}

/** The row for a field on any item, matched on both kind and key. */
export function findItemField(
	catalogue: Catalogue,
	kind: string,
	key: string
): AnyField | undefined {
	return anyTypeFields(catalogue).find((f) => f.kind === kind && f.key === key);
}

/** Convert a field on any item to a `FieldInfo`, with a type field's options when one has it. */
export function itemFieldInfo(catalogue: Catalogue, kind: string, key: string): FieldInfo {
	const found = findItemField(catalogue, kind, key);
	const label = found?.label ?? key;
	const prop = found?.prop;
	return {
		type: '',
		typeLabel: ITEM_FIELDS_LABEL,
		key,
		label,
		kind,
		prop: prop ?? itemFieldProp(kind, key, label),
		archived: false,
		typedChoice: prop === undefined && TYPED_TEXT_KINDS.has(kind)
	};
}

/** The saved fields, and their table columns, a condition may be about. */
export function savedFieldInfos(catalogue: Catalogue): FieldInfo[] {
	const out: FieldInfo[] = [];
	for (const saved of catalogue.savedFields ?? []) {
		const kind = kindOf(saved.property);
		if (!kind) continue;
		const base = {
			type: '',
			typeLabel: SAVED_FIELDS_LABEL,
			key: '',
			archived: false,
			origin: saved.id
		};
		if (operatorsForKind(kind).length > 0)
			out.push({ ...base, label: saved.label, kind, prop: saved.property });
		const prop = saved.property;
		if (kind !== 'group' || prop.type !== 'array' || !isRec(prop.items)) continue;
		for (const [subKey, sub] of propertiesOf(prop.items)) {
			const subKind = kindOf(sub);
			if (!subKind || operatorsForKind(subKind).length === 0) continue;
			const label = `${saved.label} › ${title(sub, subKey)}`;
			out.push({ ...base, subKey, label, kind: subKind, prop: sub });
		}
	}
	return out;
}

export function findSavedField(
	catalogue: Catalogue,
	origin: string,
	subKey?: string
): FieldInfo | undefined {
	return savedFieldInfos(catalogue).find(
		(f) => f.origin === origin && (f.subKey ?? undefined) === (subKey ?? undefined)
	);
}

/** The picker value for a saved field or one of its columns: `saved:<id>[:<column>]`. */
export function savedFieldSubject(origin: string, subKey?: string): string {
	return subKey === undefined ? `saved:${origin}` : `saved:${origin}:${subKey}`;
}

/** Inverse of `savedFieldSubject`; ids have no colons, columns may. */
export function parseSavedFieldSubject(
	subject: string
): { origin: string; subKey?: string } | null {
	const match = /^saved:([^:]+)(?::(.+))?$/s.exec(subject);
	if (!match) return null;
	return match[2] === undefined ? { origin: match[1] } : { origin: match[1], subKey: match[2] };
}

/** Kinds whose per-item value is typed text, because the listing carries no option list (R17). */
const TYPED_TEXT_KINDS: ReadonlySet<string> = new Set(['choice', 'multichoice']);

/** The property the kind's own editor would write, so its input widget accepts it. */
function itemFieldProp(kind: string, key: string, label: string): JsonSchemaProperty {
	const descriptor = TYPED_TEXT_KINDS.has(kind) ? undefined : getDescriptor(kind);
	const schema = descriptor?.toSchema({
		key,
		label,
		kind,
		required: false,
		options: [],
		subFields: []
	}) ?? { title: label, type: 'string' };
	return withPropMeta(schema, { kind });
}

export type ItemFieldOption = { value: string; label: string; kind: string; count: number };

/** The "Any item type" group for the field picker; null when there is nothing to offer. */
export function itemFieldGroup(
	catalogue: Catalogue
): { label: string; options: ItemFieldOption[] } | null {
	const options = anyTypeFields(catalogue)
		.filter((f) => operatorsForKind(f.kind).length > 0)
		.map((f) => ({
			value: itemFieldSubject(f.kind, f.key),
			label: f.label,
			kind: f.kind,
			count: f.count
		}));
	return options.length > 0 ? { label: ITEM_FIELDS_LABEL, options } : null;
}

/** The picker value for a per-item field: `item:<kind>:<key>`. */
export function itemFieldSubject(kind: string, key: string): string {
	return `item:${kind}:${key}`;
}

/** Inverse of `itemFieldSubject`; null for anything else. Keys may contain colons, kinds do not. */
export function parseItemFieldSubject(subject: string): { kind: string; key: string } | null {
	const match = /^item:([^:]+):(.+)$/s.exec(subject);
	return match ? { kind: match[1], key: match[2] } : null;
}

export function findField(
	catalogue: Catalogue,
	type: string,
	key: string,
	subKey?: string
): FieldInfo | undefined {
	return catalogue.fields.find(
		(f) => f.type === type && f.key === key && (f.subKey ?? undefined) === (subKey ?? undefined)
	);
}

/** Fields a condition may be about: not archived, and of a kind with operators. */
export function filterableFields(catalogue: Catalogue): FieldInfo[] {
	return catalogue.fields.filter((f) => !f.archived && operatorsForKind(f.kind).length > 0);
}

/** Top-level fields the server can sort on. */
export function sortableFields(catalogue: Catalogue): FieldInfo[] {
	return catalogue.fields.filter((f) => !f.archived && !f.subKey && SORTABLE_KINDS.has(f.kind));
}

/** Other top-level fields of the same kind on the same type, for "compare with another field". */
export function refCandidates(catalogue: Catalogue, field: FieldInfo): FieldInfo[] {
	if (field.subKey || !REF_KINDS.has(field.kind)) return [];
	return catalogue.fields.filter(
		(f) =>
			f.type === field.type &&
			!f.subKey &&
			!f.archived &&
			f.kind === field.kind &&
			f.key !== field.key
	);
}

export function canCompareWithField(catalogue: Catalogue, field: FieldInfo | undefined): boolean {
	return field !== undefined && refCandidates(catalogue, field).length > 0;
}

/** Fields grouped by item type, in type order, for grouped selects. */
export function groupByType(
	catalogue: Catalogue,
	fields: FieldInfo[]
): { slug: string; label: string; fields: FieldInfo[] }[] {
	return catalogue.types
		.map((t) => ({ ...t, fields: fields.filter((f) => f.type === t.slug) }))
		.filter((g) => g.fields.length > 0);
}

/** A plain value as the cards show it ("45:00", "£3.50", "1984", "4 stars"); null when unknown. */
export function formatFieldValue(field: FieldInfo, value: unknown): string | null {
	if (field.kind === 'rating' && typeof value === 'number')
		return `${value} ${value === 1 ? 'star' : 'stars'}`;
	if (field.kind === 'boolean' && typeof value === 'boolean') return value ? 'yes' : 'no';
	const text = coreForProp(field.prop)?.formatSummary?.(value, field.prop);
	return typeof text === 'string' && text !== '' ? text : null;
}

/** Labels and value formatting for `describeCondition`, read from the item types. */
export function summaryLookup(
	catalogue: Catalogue,
	collectionName?: SummaryLookup['collectionName'],
	connections: Pick<SummaryLookup, 'relationship' | 'itemName'> = {}
): SummaryLookup {
	return {
		collectionName,
		...connections,
		typeLabel: (slug) => typeLabel(catalogue, slug),
		fieldLabel: (type, key) => findField(catalogue, type, key)?.label ?? key,
		itemFieldLabel: (kind, key) => findItemField(catalogue, kind, key)?.label ?? key,
		savedFieldLabel: (origin, subKey) => findSavedField(catalogue, origin, subKey)?.label ?? null,
		savedFieldKind: (origin, subKey) => findSavedField(catalogue, origin, subKey)?.kind ?? null,
		formatSavedValue: (origin, subKey, value) => {
			const field = findSavedField(catalogue, origin, subKey);
			return field ? formatFieldValue(field, value) : null;
		},
		subFieldLabel: (type, key, subKey) => findField(catalogue, type, key, subKey)?.label ?? null,
		fieldKind: (type, key, subKey) => findField(catalogue, type, key, subKey)?.kind ?? null,
		formatValue: (type, key, subKey, value) => {
			const field = findField(catalogue, type, key, subKey);
			return field ? formatFieldValue(field, value) : null;
		},
		formatItemValue: (kind, key, value) =>
			formatFieldValue(itemFieldInfo(catalogue, kind, key), value)
	};
}
