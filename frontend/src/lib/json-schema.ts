import type { PropertyMeta } from '$lib/prop-meta';

/** A property of an attributes schema (JSON Schema 2020-12 subset plus `x-menagerist`). */
type JsonSchemaPropertyBase =
	| { title: string; type: 'string'; pattern?: string; allOf?: Record<string, unknown>[] }
	| { title: string; type: 'string'; format: 'date' | 'uri' | 'email' }
	| { title: string; type: 'string'; enum: string[] }
	| { title: string; type: 'number'; minimum?: number; maximum?: number; multipleOf?: number }
	| { title: string; type: 'boolean' }
	| {
			title: string;
			type: 'array';
			items: { type: 'object'; properties: Record<string, JsonSchemaProperty> };
	  }
	| {
			title: string;
			type: 'array';
			items: { type: 'string'; enum?: string[] };
			uniqueItems?: boolean;
	  }
	| { title: string; type: 'object'; properties: Record<string, JsonSchemaProperty> };

export type JsonSchemaProperty = JsonSchemaPropertyBase & { 'x-menagerist'?: PropertyMeta };
