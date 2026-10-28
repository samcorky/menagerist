/**
 * Accessors for a property's `x-menagerist` metadata. Standard JSON Schema keywords describe
 * validation; this namespace describes everything else. Nothing else reads `x-*` keys.
 * Kept free of schema-editor types so any screen can import it.
 */
export const NAMESPACE = 'x-menagerist';

export type PropertyMeta = {
	kind?: string;
	display?: string;
	archived?: boolean;
	search?: boolean;
	suggest?: boolean;
	config?: Record<string, unknown>;
	/** A `group` (table) field's sub-property keys in order. See `field-types/group/columns.ts`. */
	columns?: string[];
	/** A `list` field's items are edited/shown as a growing textarea rather than one line. */
	multiline?: boolean;
	/** A choice field linked to a saved list (its id). The options come from that list. */
	list?: string;
	/** Unknown members are preserved on round-trip. */
	[member: string]: unknown;
};

/** Read the `x-menagerist` members of a schema or property. Returns `{}` when absent or malformed. */
export function readMeta<T extends object>(node: unknown): T {
	if (typeof node !== 'object' || node === null) return {} as T;
	const meta = (node as Record<string, unknown>)[NAMESPACE];
	if (typeof meta !== 'object' || meta === null || Array.isArray(meta)) return {} as T;
	return { ...meta } as T;
}

/** Read a property's metadata. Returns `{}` when absent or malformed. */
export function readPropMeta(prop: object | null | undefined): PropertyMeta {
	return readMeta<PropertyMeta>(prop);
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
