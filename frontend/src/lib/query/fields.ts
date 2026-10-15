import { descriptorForProp } from '$lib/field-types';
import { readPropMeta } from '$lib/schema-meta';
import type { JsonSchemaProperty } from '$lib/schema-types';
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
};

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
};

function isRec(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function kindOf(prop: JsonSchemaProperty): string | null {
	try {
		return descriptorForProp(prop)?.kind ?? null;
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
export function buildCatalogue(itemTypes: readonly ItemTypeLike[], loaded = true): Catalogue {
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
	return { types: itemTypes.map((t) => ({ slug: t.slug, label: t.label })), fields, loaded };
}

export function typeLabel(catalogue: Catalogue, slug: string): string {
	return catalogue.types.find((t) => t.slug === slug)?.label ?? slug;
}

/** "Film › Rating" for a field reference, from the catalogue when it is known. */
export function fieldReferenceLabel(
	catalogue: Catalogue,
	type: string,
	key: string,
	subKey?: string
): string {
	const field = findField(catalogue, type, key, subKey);
	const name = field?.label ?? (subKey ? `${key} › ${subKey}` : key);
	return `${typeLabel(catalogue, type)} › ${name}`;
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
	const text = descriptorForProp(field.prop)?.formatSummary?.(value, field.prop);
	return typeof text === 'string' && text !== '' ? text : null;
}

/** Labels and value formatting for `describeCondition`, read from the item types. */
export function summaryLookup(catalogue: Catalogue): SummaryLookup {
	return {
		typeLabel: (slug) => typeLabel(catalogue, slug),
		fieldLabel: (type, key) => findField(catalogue, type, key)?.label ?? key,
		subFieldLabel: (type, key, subKey) => findField(catalogue, type, key, subKey)?.label ?? null,
		fieldKind: (type, key, subKey) => findField(catalogue, type, key, subKey)?.kind ?? null,
		formatValue: (type, key, subKey, value) => {
			const field = findField(catalogue, type, key, subKey);
			return field ? formatFieldValue(field, value) : null;
		}
	};
}
