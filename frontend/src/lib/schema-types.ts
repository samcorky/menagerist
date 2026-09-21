import type { XLayout } from '$lib/layout';

export type JsonSchemaProperty =
	| { title: string; type: 'string'; 'x-multiline'?: true }
	| { title: string; type: 'string'; format: 'date' }
	| { title: string; type: 'string'; enum: string[] }
	| { title: string; type: 'number' }
	| { title: string; type: 'boolean' }
	| {
			title: string;
			type: 'array';
			items: { type: 'object'; properties: Record<string, JsonSchemaProperty> };
	  };

export type AttributesSchema = {
	$schema: 'https://json-schema.org/draft/2020-12/schema';
	type: 'object';
	properties: Record<string, JsonSchemaProperty>;
	required?: string[];
	'x-layout'?: XLayout;
};

export type EditorSubField = {
	key: string;
	label: string;
	kind: string;
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
	/** Original property for the `opaque` kind, written back unchanged on save. */
	raw?: Record<string, unknown>;
};
