import { describe, it, expect } from 'vitest';
import {
	itemsToSchema,
	schemaToArchived,
	schemaToItems,
	settleSchema
} from '$lib/schema-editor-items';
import { readSchemaMeta } from '$lib/schema-meta';
import type { AttributesSchema } from '$lib/schema-types';

// What the API returns for a type made with one plain field and no editor metadata.
const stored = {
	type: 'object',
	properties: {
		rating: { type: 'string', title: 'Rating', 'x-menagerist': { kind: 'text' } }
	}
} as unknown as AttributesSchema;

// What the schema editor writes back as soon as it has opened that schema.
function whatTheEditorWrites(
	schema: AttributesSchema | null,
	list: 'card' | 'connection' = 'card'
) {
	return itemsToSchema(
		schemaToItems(schema, list),
		readSchemaMeta(schema),
		schemaToArchived(schema),
		list
	);
}

describe('settleSchema', () => {
	it('is what the editor writes when it opens a stored schema', () => {
		expect(settleSchema(stored)).toEqual(whatTheEditorWrites(stored));
	});

	it('differs from a stored schema the editor would rewrite', () => {
		// This difference is what made an untouched editor look changed.
		expect(settleSchema(stored)).not.toEqual(stored);
	});

	it('does not change again when the editor opens it', () => {
		const once = settleSchema(stored);
		expect(whatTheEditorWrites(once)).toEqual(once);
		expect(settleSchema(once)).toEqual(once);
	});

	it('keeps the fields, their kinds and their order', () => {
		const settled = settleSchema(stored);
		expect(Object.keys(settled?.properties ?? {})).toEqual(['rating']);
		expect(settled?.properties.rating.title).toBe('Rating');
	});

	it('follows the list the editor uses, as connection types do', () => {
		expect(settleSchema(stored, 'connection')).toEqual(whatTheEditorWrites(stored, 'connection'));
		const once = settleSchema(stored, 'connection');
		expect(settleSchema(once, 'connection')).toEqual(once);
	});

	it('leaves no schema as no schema', () => {
		expect(settleSchema(null)).toBeNull();
		expect(whatTheEditorWrites(null)).toBeNull();
	});

	it('keeps archived fields and unknown root members', () => {
		const withExtras = {
			...stored,
			properties: {
				...stored.properties,
				old: {
					type: 'string',
					title: 'Old',
					'x-menagerist': { kind: 'text', archived: true }
				}
			},
			'x-menagerist': { version: 1, custom: { keep: 'me' } }
		} as unknown as AttributesSchema;
		const settled = settleSchema(withExtras);
		expect(settled?.properties.old).toBeDefined();
		expect(readSchemaMeta(settled)).toMatchObject({ custom: { keep: 'me' } });
		expect(settleSchema(settled)).toEqual(settled);
	});
});
