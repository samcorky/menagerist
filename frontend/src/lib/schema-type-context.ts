/** Which saved type the schema editor is editing, for extras that need to query usage. */
export type SchemaTypeContext = {
	readonly typeId: string | undefined;
	readonly kind: 'node' | 'edge';
};

export const SCHEMA_TYPE_CONTEXT = Symbol('schema-type');
