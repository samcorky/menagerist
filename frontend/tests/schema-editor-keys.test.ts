import { describe, it, expect } from 'vitest';
import {
	itemsToSchema,
	schemaToArchived,
	schemaToItems,
	type EditorItem
} from '../src/lib/schema-editor-items';
import { archiveField, restoreField } from '../src/lib/field-archive';
import type { AttributesSchema, EditorField } from '../src/lib/schema-types';

const newField = (label: string, extra: Partial<EditorField> = {}): EditorField => ({
	key: `placeholder-${label}`,
	label,
	kind: 'text',
	required: false,
	options: [],
	subFields: [],
	keyPending: true,
	...extra
});

const keysOf = (schema: AttributesSchema | null) => Object.keys(schema?.properties ?? {});

describe('editor keys', () => {
	it('a new field titled Director gets the key director', () => {
		expect(keysOf(itemsToSchema([newField('Director')], {}))).toEqual(['director']);
	});

	it('renaming a saved field label keeps its key and stored data mapping', () => {
		const saved = itemsToSchema([newField('Director')], {})!;
		const items = schemaToItems(saved).map((i) => ({ ...i, label: 'Filmmaker' }) as EditorItem);
		const next = itemsToSchema(items, {})!;
		expect(keysOf(next)).toEqual(['director']);
		expect(next.properties.director.title).toBe('Filmmaker');
	});

	it('a second Director gets director_2, and so does one next to an archived director', () => {
		expect(keysOf(itemsToSchema([newField('Director'), newField('Director')], {}))).toEqual([
			'director',
			'director_2'
		]);
		const archived: AttributesSchema = {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties: {
				director: { title: 'Director', type: 'string', 'x-menagerist': { archived: true } }
			}
		};
		const items = [...schemaToItems(archived), newField('Director')];
		expect(keysOf(itemsToSchema(items, {}, schemaToArchived(archived)))).toEqual([
			'director_2',
			'director'
		]);
	});

	it('a non-Latin title gives field, then field_2', () => {
		expect(keysOf(itemsToSchema([newField('監督'), newField('#')], {}))).toEqual([
			'field',
			'field_2'
		]);
	});

	it('mixed UUID and slug keys load, edit and keep the required marker', () => {
		const uuid = '3f0c6d1e-8f5b-4c0e-9a51-2b7d9d0f1a11';
		const legacy: EditorField = { ...newField('Legacy'), key: uuid, keyPending: false };
		const schema = itemsToSchema([legacy, newField('Notes', { required: true })], {})!;
		expect(keysOf(schema)).toEqual([uuid, 'notes']);
		expect(schema['x-menagerist']?.required).toEqual(['notes']);
		expect(schema).not.toHaveProperty('required');
	});

	it('sub-field keys are unique within their group', () => {
		const group = newField('Cast', {
			kind: 'group',
			subFields: [
				{ key: 'p1', label: 'Name', kind: 'text', keyPending: true },
				{ key: 'p2', label: 'Name', kind: 'text', keyPending: true }
			]
		});
		const schema = itemsToSchema([group], {})!;
		const cast = schema.properties.cast;
		expect(cast.type === 'array' && Object.keys(cast.items.properties)).toEqual(['name', 'name_2']);
	});

	it('a __proto__ key is kept as an own property and does not change the prototype', () => {
		const props = JSON.parse(
			'{"__proto__": {"title": "Odd", "type": "string"}, "ok": {"title": "Ok", "type": "string"}}'
		);
		const schema = {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties: props
		} as AttributesSchema;
		const out = itemsToSchema(schemaToItems(schema), {})!;
		expect(Object.getPrototypeOf(out.properties)).toBe(Object.prototype);
		expect(Object.keys(out.properties)).toContain('__proto__');
	});
});

describe('archived fields', () => {
	const saved = (key: string, label: string): EditorField => ({
		key,
		label,
		kind: 'text',
		required: false,
		options: [],
		subFields: []
	});

	it('an archived field stays in properties but leaves the layout and required', () => {
		const items = [saved('year', 'Year')];
		const archived = [archiveField({ ...saved('old', 'Old'), required: true })];
		const schema = itemsToSchema(items, {}, archived)!;
		expect(Object.keys(schema.properties)).toEqual(['year', 'old']);
		expect(schema.properties.old['x-menagerist']?.archived).toBe(true);
		expect(schema['x-menagerist']?.layout).toEqual([{ key: 'year' }]);
		expect(schema['x-menagerist']?.required).toEqual([]);
	});

	it('round-trips: archived fields are split out on load and written back untouched', () => {
		const items = [saved('year', 'Year')];
		const first = itemsToSchema(items, {}, [archiveField(saved('old', 'Old'))])!;
		expect(schemaToItems(first).map((i) => (i as EditorField).key)).toEqual(['year']);
		const archived = schemaToArchived(first);
		expect(archived.map((f) => f.key)).toEqual(['old']);
		expect(itemsToSchema(schemaToItems(first), {}, archived)).toEqual(first);
	});

	it('restoring brings the field back with its key and clears the flag', () => {
		const first = itemsToSchema([], {}, [archiveField(saved('old', 'Old'))])!;
		const [field] = schemaToArchived(first);
		const restored = itemsToSchema([restoreField(field)], {}, [])!;
		expect(Object.keys(restored.properties)).toEqual(['old']);
		expect(restored.properties.old['x-menagerist']?.archived).toBeUndefined();
	});

	it('a new field with the same title as an archived one gets a suffixed key', () => {
		const archived = [archiveField(saved('director', 'Director'))];
		const schema = itemsToSchema([newField('Director')], {}, archived)!;
		expect(keysOf(schema)).toEqual(['director_2', 'director']);
	});

	it('a schema with only archived fields is still written', () => {
		expect(itemsToSchema([], {}, [archiveField(saved('old', 'Old'))])).not.toBeNull();
	});
});
