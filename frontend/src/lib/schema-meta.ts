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
	/** Unknown members are preserved on round-trip. */
	[member: string]: unknown;
};

export type SchemaMeta = {
	version?: number;
	layout?: XLayout;
	required?: string[];
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
