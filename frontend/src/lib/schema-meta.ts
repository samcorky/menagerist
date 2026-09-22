import type { XLayout } from '$lib/layout';

/**
 * Accessors for the `x-menagerist` namespace. Standard JSON Schema keywords describe
 * validation; this namespace describes everything else. Nothing else reads `x-*` keys.
 */
export const NAMESPACE = 'x-menagerist';
export const META_VERSION = 1;

export type PropertyMeta = {
	kind?: string;
	display?: string;
	archived?: boolean;
	search?: boolean;
	suggest?: boolean;
	config?: Record<string, unknown>;
	/** A `group` (table) field's sub-property keys in order. See `field-types/group/columns.ts`. */
	columns?: string[];
	/** Unknown members are preserved on round-trip. */
	[member: string]: unknown;
};

export type HighlightEntry = { key: string };

/** Which highlight list: an item type's cards, or a relationship type's connection rows. */
export type HighlightList = 'card' | 'connection';

export type SchemaMeta = {
	version?: number;
	layout?: XLayout;
	required?: string[];
	/** Fields shown on cards (`card`); other lists (for example `connection`) are preserved. */
	highlights?: {
		card?: HighlightEntry[];
		connection?: HighlightEntry[];
		[list: string]: unknown;
	};
	/** Unknown members are preserved on round-trip. */
	[member: string]: unknown;
};

function readMeta<T extends object>(node: unknown): T {
	if (typeof node !== 'object' || node === null) return {} as T;
	const meta = (node as Record<string, unknown>)[NAMESPACE];
	if (typeof meta !== 'object' || meta === null || Array.isArray(meta)) return {} as T;
	return { ...meta } as T;
}

/** Read a schema's root metadata. Returns `{}` when absent or malformed. */
export function readSchemaMeta(schema: object | null | undefined): SchemaMeta {
	return readMeta<SchemaMeta>(schema);
}

/** Read a property's metadata. Returns `{}` when absent or malformed. */
export function readPropMeta(prop: object | null | undefined): PropertyMeta {
	return readMeta<PropertyMeta>(prop);
}

/** Return a copy of `schema` with `patch` merged into its root metadata. */
export function withSchemaMeta<T extends object>(schema: T, patch: SchemaMeta): T {
	return { ...schema, [NAMESPACE]: { ...readSchemaMeta(schema), ...patch } };
}

/** Return a copy of `prop` with `patch` merged into its metadata. */
export function withPropMeta<T extends object>(prop: T, patch: PropertyMeta): T {
	return { ...prop, [NAMESPACE]: { ...readPropMeta(prop), ...patch } };
}

/** Return a copy of `prop` with its metadata replaced wholesale, not merged. */
export function replacePropMeta<T extends object>(prop: T, meta: PropertyMeta): T {
	const copy = { ...prop } as Record<string, unknown>;
	if (Object.keys(meta).length > 0) copy[NAMESPACE] = meta;
	else delete copy[NAMESPACE];
	return copy as T;
}

/** A stored highlight list, in order. Malformed entries are skipped. */
export function readHighlights(
	schema: object | null | undefined,
	list: HighlightList = 'card'
): HighlightEntry[] {
	const entries = readSchemaMeta(schema).highlights?.[list];
	if (!Array.isArray(entries)) return [];
	return entries.flatMap((e) =>
		typeof e === 'object' && e !== null && typeof (e as HighlightEntry).key === 'string'
			? [{ key: (e as HighlightEntry).key }]
			: []
	);
}

/** Return a copy of `schema` with one highlight list replaced. Other lists are kept. */
export function withHighlights<T extends object>(
	schema: T,
	entries: HighlightEntry[],
	list: HighlightList = 'card'
): T {
	const { [list]: _previous, ...others } = readSchemaMeta(schema).highlights ?? {};
	const highlights = entries.length > 0 ? { ...others, [list]: entries } : others;
	const meta = { ...readSchemaMeta(schema) };
	if (Object.keys(highlights).length > 0) meta.highlights = highlights;
	else delete meta.highlights;
	return { ...schema, [NAMESPACE]: meta };
}

/** Keys of top-level properties marked archived: hidden from forms, data kept. */
export function archivedKeys(schema: { properties?: Record<string, unknown> } | null): Set<string> {
	return new Set(
		Object.entries(schema?.properties ?? {})
			.filter(([, prop]) => readPropMeta(prop as object).archived === true)
			.map(([key]) => key)
	);
}

/**
 * Return a copy of `schema` for client-side validation. A standard root `required` array
 * (for example from a schema authored through the API) and archived properties are dropped:
 * required is advisory and archived fields are hidden, so neither may produce a blocking
 * error. Mirrors the backend's `validation_schema`.
 */
export function validationSchema<T extends object>(schema: T): T {
	const copy: Record<string, unknown> = { ...(schema as Record<string, unknown>) };
	delete copy.required;
	const properties = copy.properties as Record<string, unknown> | undefined;
	if (properties) {
		const archived = archivedKeys({ properties });
		copy.properties = Object.fromEntries(
			Object.entries(properties).filter(([k]) => !archived.has(k))
		);
	}
	return copy as T;
}
