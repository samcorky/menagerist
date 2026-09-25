import { readPropMeta } from '$lib/schema-meta';
import type { JsonSchemaProperty } from '$lib/schema-types';

/**
 * A table (group) field's sub-properties in their saved order.
 *
 * Postgres JSONB does not preserve object key order, so `Object.entries` on a
 * property freshly loaded from the API is not reliable column order. The
 * explicit `columns` member read via `readPropMeta` (written by `group.ts`'s
 * `toSchema`) is the source of truth; a schema saved before this existed, or
 * edited through the API, falls back to whatever order the properties come in.
 */
export function orderedColumns(prop: JsonSchemaProperty): [string, JsonSchemaProperty][] {
	if (prop.type !== 'array' || prop.items.type !== 'object') return [];
	const properties = (prop.items.properties ?? {}) as Record<string, JsonSchemaProperty>;
	const order = readPropMeta(prop).columns;
	if (!Array.isArray(order)) return Object.entries(properties);
	const known = order.filter((k): k is string => typeof k === 'string' && k in properties);
	const rest = Object.keys(properties).filter((k) => !known.includes(k));
	return [...known, ...rest].map((k) => [k, properties[k]]);
}
