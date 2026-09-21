import { descriptorForProp } from '$lib/field-types';
import { readPropMeta } from '$lib/schema-meta';
import type { AttributesSchema, JsonSchemaProperty } from '$lib/schema-types';

export type MatchContext = { label: string; text: string };

/** Every string and number inside a value (never keys, booleans or nulls), in order. */
function scalars(value: unknown): string[] {
	if (typeof value === 'string') return [value];
	if (typeof value === 'number') return [String(value)];
	if (Array.isArray(value)) return value.flatMap(scalars);
	if (typeof value === 'object' && value !== null) return Object.values(value).flatMap(scalars);
	return [];
}

/** Mirrors the server: archived, opted-out and non-searchable fields are never searched. */
function isSearchable(prop: JsonSchemaProperty): boolean {
	const meta = readPropMeta(prop);
	if (meta.archived === true || meta.search === false) return false;
	return descriptorForProp(prop)?.searchable !== false;
}

/**
 * Why an item matched a search, when the reason is not its name or description: the label of the
 * first field whose value contains the text, and that value (the cell text for a table).
 * Returns null when the name or description matched, or nothing visible did.
 */
export function matchContext(
	item: { name: string; description?: string | null; attributes?: Record<string, unknown> | null },
	schema: AttributesSchema | null | undefined,
	q: string
): MatchContext | null {
	const needle = q.trim().toLowerCase();
	if (!needle) return null;
	if (item.name.toLowerCase().includes(needle)) return null;
	if ((item.description ?? '').toLowerCase().includes(needle)) return null;

	const attributes = item.attributes ?? {};
	const properties = schema?.properties ?? {};
	const known = Object.keys(properties).filter((key) => key in attributes);
	const unknown = Object.keys(attributes).filter((key) => !Object.hasOwn(properties, key));
	for (const key of [...known, ...unknown]) {
		const prop = Object.hasOwn(properties, key) ? properties[key] : undefined;
		if (prop && !isSearchable(prop)) continue;
		const text = scalars(attributes[key]).find((s) => s.toLowerCase().includes(needle));
		if (text !== undefined) return { label: prop?.title || key, text };
	}
	return null;
}
