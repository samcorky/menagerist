import { describe, it, expect } from 'vitest';
import {
	fieldToDefinition,
	linkToList,
	linkedListId,
	listUpdateAvailable,
	unlinkField,
	type Preset
} from '../src/lib/presets';
import { propertyFromField } from '../src/lib/field-types';
import { itemsToSchema, schemaToItems, type EditorItem } from '../src/lib/schema-editor-items';
import { readPropMeta } from '../src/lib/schema-meta';
import type { AttributesSchema, EditorField } from '../src/lib/schema-types';

const field = (extra: Partial<EditorField> = {}): EditorField => ({
	key: 'grade',
	label: 'Grade',
	kind: 'choice',
	required: false,
	options: ['Mint', 'VG+'],
	subFields: [],
	...extra
});

const preset: Preset = {
	id: 'list-1',
	kind: 'choice_list',
	label: 'Grades',
	description: null,
	definition: { options: ['Mint', 'Near mint', 'Good'] },
	version: 4,
	builtin: false
};

describe('linking a choice field to a saved list', () => {
	it('takes the list options and records the reference without a copy origin', () => {
		const linked = linkToList(field({ meta: { origin: { preset: 'old', version: 1 } } }), preset);

		expect(linked.options).toEqual(['Mint', 'Near mint', 'Good']);
		expect(linkedListId(linked)).toBe('list-1');
		expect(linked.meta?.origin).toBeUndefined();
	});

	it('writes x-menagerist.list and no enum', () => {
		const prop = propertyFromField(linkToList(field(), preset));

		expect(prop).toEqual({
			title: 'Grade',
			type: 'string',
			'x-menagerist': { kind: 'choice', list: 'list-1' }
		});
		expect('enum' in prop).toBe(false);
	});

	it('writes no enum when the whole schema is saved', () => {
		const items: EditorItem[] = [linkToList(field(), preset)];
		const schema = itemsToSchema(items, {})!;

		expect('enum' in schema.properties.grade).toBe(false);
		expect(readPropMeta(schema.properties.grade).list).toBe('list-1');
	});

	it('restores the link and resolved options when the schema is read back', () => {
		// The API resolves `enum` from the list on read; the link must survive too.
		const schema: AttributesSchema = {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties: {
				grade: {
					title: 'Grade',
					type: 'string',
					enum: ['Mint', 'Near mint', 'Good'],
					'x-menagerist': { kind: 'choice', list: 'list-1' }
				}
			}
		};
		const [loaded] = schemaToItems(schema) as EditorField[];

		expect(loaded.kind).toBe('choice');
		expect(loaded.options).toEqual(['Mint', 'Near mint', 'Good']);
		expect(linkedListId(loaded)).toBe('list-1');
		expect(listUpdateAvailable(loaded, { ...preset, version: 9 })).toBe(false);
	});

	it('round-trips a linked field without copying its options', () => {
		const schema = itemsToSchema([linkToList(field(), preset)], {})!;
		const resolved: AttributesSchema = {
			...schema,
			properties: {
				grade: {
					title: 'Grade',
					type: 'string',
					enum: ['Mint', 'Near mint', 'Good'],
					'x-menagerist': { kind: 'choice', list: 'list-1' }
				}
			}
		};
		const written = itemsToSchema(schemaToItems(resolved), {})!;

		expect('enum' in written.properties.grade).toBe(false);
		expect(readPropMeta(written.properties.grade).list).toBe('list-1');
	});
});

describe('unlinking a choice field', () => {
	it('keeps the options as a copy and writes them as an enum again', () => {
		const copy = unlinkField(linkToList(field(), preset));

		expect(linkedListId(copy)).toBeUndefined();
		expect(copy.options).toEqual(['Mint', 'Near mint', 'Good']);
		expect(propertyFromField(copy)).toEqual({
			title: 'Grade',
			type: 'string',
			enum: ['Mint', 'Near mint', 'Good'],
			'x-menagerist': { kind: 'choice' }
		});
	});
});

describe('copy-based choice fields', () => {
	it('still write their options as an enum', () => {
		expect(propertyFromField(field())).toEqual({
			title: 'Grade',
			type: 'string',
			enum: ['Mint', 'VG+'],
			'x-menagerist': { kind: 'choice' }
		});
	});
});

describe('saving a linked field as a field preset', () => {
	it('copies the options in and drops the list reference', () => {
		const preset = {
			id: 'p1',
			kind: 'choice_list',
			version: 1,
			label: 'Grades',
			definition: { options: ['Mint', 'Good'] }
		} as unknown as Preset;
		const { property } = fieldToDefinition(linkToList(field({ kind: 'choice' }), preset));
		expect((property as { enum?: unknown }).enum).toEqual(['Mint', 'Good']);
		expect(readPropMeta(property).list).toBeUndefined();
	});
});
