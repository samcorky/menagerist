import type { PropertyMeta, SchemaMeta } from '$lib/schema-meta';

type JsonSchemaPropertyBase =
	| { title: string; type: 'string' }
	| { title: string; type: 'string'; format: 'date' }
	| { title: string; type: 'string'; enum: string[] }
	| { title: string; type: 'number'; minimum?: number; maximum?: number; multipleOf?: number }
	| { title: string; type: 'boolean' }
	| {
			title: string;
			type: 'array';
			items: { type: 'object'; properties: Record<string, JsonSchemaProperty> };
	  };

export type JsonSchemaProperty = JsonSchemaPropertyBase & { 'x-menagerist'?: PropertyMeta };

export type AttributesSchema = {
	$schema: 'https://json-schema.org/draft/2020-12/schema';
	type: 'object';
	properties: Record<string, JsonSchemaProperty>;
	'x-menagerist'?: SchemaMeta;
};

export type EditorSubField = {
	key: string;
	label: string;
	kind: string;
	/** True until the schema is saved: the key is still derived from the label. */
	keyPending?: boolean;
	/** Kind when loaded from a saved schema; limits which kinds it may change to. */
	originalKind?: string;
	meta?: PropertyMeta;
	/** Original property for the `opaque` kind, written back unchanged on save. */
	raw?: Record<string, unknown>;
};

export type EditorField = {
	key: string;
	label: string;
	kind: string;
	required: boolean;
	options: string[];
	subFields: EditorSubField[];
	/** True until the schema is saved: the key is still derived from the label. */
	keyPending?: boolean;
	/** Kind when loaded from a saved schema; limits which kinds it may change to. */
	originalKind?: string;
	/** Metadata members carried through unchanged (display, archived, unknown members). */
	meta?: PropertyMeta;
	/** Original property for the `opaque` kind, written back unchanged on save. */
	raw?: Record<string, unknown>;
};
