import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';
import { allDescriptors, descriptorForProp, getDescriptor } from '../src/lib/field-types/index';
import { fieldFromProperty, propertyFromField } from '../src/lib/field-types/registry';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

const EXPECTED_KINDS = ['text', 'number', 'boolean', 'date', 'longtext', 'choice', 'group'];

describe('all built-in kinds are registered', () => {
	const kinds = allDescriptors().map((d) => d.kind);
	for (const kind of EXPECTED_KINDS) {
		it(`registers "${kind}"`, () => {
			expect(kinds).toContain(kind);
		});
	}
});

describe('descriptorForProp matching', () => {
	const cases: [string, JsonSchemaProperty][] = [
		['text', { title: 'Name', type: 'string' }],
		['number', { title: 'Price', type: 'number' }],
		['boolean', { title: 'Active', type: 'boolean' }],
		['date', { title: 'Published', type: 'string', format: 'date' }],
		['longtext', { title: 'Notes', type: 'string', 'x-menagerist': { kind: 'longtext' } }],
		['choice', { title: 'Status', type: 'string', enum: ['Draft', 'Published'] }],
		[
			'group',
			{
				title: 'Cast',
				type: 'array',
				items: { type: 'object', properties: { name: { title: 'Name', type: 'string' } } }
			}
		]
	];

	for (const [expectedKind, prop] of cases) {
		it(`matches "${expectedKind}" for ${JSON.stringify({ type: prop.type })}`, () => {
			expect(descriptorForProp(prop)?.kind).toBe(expectedKind);
		});
	}
});

describe('text does not match specialised string props', () => {
	it('does not match date prop', () => {
		const dateProp: JsonSchemaProperty = { title: 'X', type: 'string', format: 'date' };
		expect(getDescriptor('text')!.fromSchema('x', dateProp, false)).toBeNull();
	});

	it('does not infer longtext from shape alone', () => {
		expect(descriptorForProp({ title: 'X', type: 'string' })?.kind).toBe('text');
	});

	it('does not match choice prop', () => {
		const choiceProp: JsonSchemaProperty = { title: 'X', type: 'string', enum: ['A', 'B'] };
		expect(getDescriptor('text')!.fromSchema('x', choiceProp, false)).toBeNull();
	});
});

describe('toSchema / fromSchema round-trips', () => {
	it('text field round-trips', () => {
		const desc = getDescriptor('text')!;
		const field = {
			key: 'abc',
			label: 'Name',
			kind: 'text',
			required: false,
			options: [],
			subFields: []
		};
		const prop = desc.toSchema(field);
		const back = desc.fromSchema('abc', prop, false);
		expect(back?.kind).toBe('text');
		expect(back?.label).toBe('Name');
		expect(back?.key).toBe('abc');
	});

	it('choice field preserves options', () => {
		const desc = getDescriptor('choice')!;
		const field = {
			key: 'status',
			label: 'Status',
			kind: 'choice',
			required: false,
			options: ['Draft', 'Live'],
			subFields: []
		};
		const prop = desc.toSchema(field);
		const back = desc.fromSchema('status', prop, false);
		expect(back?.options).toEqual(['Draft', 'Live']);
	});

	it('group field preserves sub-field keys and labels', () => {
		const desc = getDescriptor('group')!;
		const field = {
			key: 'cast',
			label: 'Cast',
			kind: 'group',
			required: false,
			options: [],
			subFields: [{ key: 'actor-name-key', label: 'Actor', kind: 'text' }]
		};
		const prop = desc.toSchema(field);
		const back = desc.fromSchema('cast', prop, false);
		expect(back?.subFields[0].key).toBe('actor-name-key');
		expect(back?.subFields[0].label).toBe('Actor');
		expect(back?.subFields[0].kind).toBe('text');
	});

	it('required flag round-trips', () => {
		const desc = getDescriptor('number')!;
		const field = {
			key: 'price',
			label: 'Price',
			kind: 'number',
			required: true,
			options: [],
			subFields: []
		};
		const prop = desc.toSchema(field);
		const back = desc.fromSchema('price', prop, true);
		expect(back?.required).toBe(true);
	});
});

describe('opaque round-trips', () => {
	const opaque = getDescriptor('opaque')!;

	it('is not user-selectable and never matches a property', () => {
		expect(opaque.selectable).toBe(false);
		expect(descriptorForProp({ title: 'x', type: 'string' })?.kind).toBe('text');
	});

	it('keeps a string property with a format, changing only the title', () => {
		const prop = { title: 'Email', type: 'string', format: 'email' };
		expect(descriptorForProp(prop as unknown as JsonSchemaProperty)).toBeUndefined();
		const field = {
			key: 'email',
			label: 'Contact',
			kind: 'opaque',
			required: false,
			options: [],
			subFields: [],
			raw: prop
		};
		expect(opaque.toSchema(field)).toEqual({ ...prop, title: 'Contact' });
	});

	it('group keeps an enum sub-property and a format sub-property unchanged', () => {
		const group = getDescriptor('group')!;
		const prop: JsonSchemaProperty = {
			title: 'Cast',
			type: 'array',
			items: {
				type: 'object',
				properties: {
					role: { title: 'Role', type: 'string', enum: ['Lead', 'Support'] },
					mail: { title: 'Mail', type: 'string', format: 'email' } as unknown as JsonSchemaProperty,
					name: { title: 'Name', type: 'string' }
				}
			}
		};
		const field = group.fromSchema('cast', prop, false)!;
		expect(field.subFields.map((sf) => sf.kind)).toEqual(['opaque', 'opaque', 'text']);
		const written = propertyFromField(field) as Extract<JsonSchemaProperty, { type: 'array' }>;
		expect(written.items.properties).toEqual({
			...prop.items.properties,
			name: { title: 'Name', type: 'string', 'x-menagerist': { kind: 'text' } }
		});
	});

	it('group.fromSchema rejects an array of strings', () => {
		const prop = { title: 'Tags', type: 'array', items: { type: 'string' } };
		expect(
			getDescriptor('group')!.fromSchema('tags', prop as unknown as JsonSchemaProperty, false)
		).toBeNull();
	});
});

describe('explicit kind and metadata', () => {
	it('an explicit kind overrides shape inference', () => {
		const prop = { title: 'X', type: 'string', 'x-menagerist': { kind: 'longtext' } };
		expect(descriptorForProp(prop as JsonSchemaProperty)?.kind).toBe('longtext');
	});

	it('an explicit kind that does not match the shape becomes opaque', () => {
		const prop = { title: 'X', type: 'number', 'x-menagerist': { kind: 'date' } };
		expect(fieldFromProperty('x', prop as JsonSchemaProperty, false).kind).toBe('opaque');
	});

	it('an unknown kind becomes opaque and is preserved untouched', () => {
		const prop = { title: 'X', type: 'string', 'x-menagerist': { kind: 'plugin:thing' } };
		const field = fieldFromProperty('x', prop as JsonSchemaProperty, false);
		expect(field.kind).toBe('opaque');
		expect(propertyFromField(field)).toEqual(prop);
	});

	it('infers the kind from standard keywords when there is no namespace', () => {
		const prop: JsonSchemaProperty = { title: 'D', type: 'string', format: 'date' };
		expect(fieldFromProperty('d', prop, false).kind).toBe('date');
	});

	it('writes the kind and keeps display, archived and unknown members', () => {
		const prop = {
			title: 'Format',
			type: 'string',
			enum: ['LP'],
			'x-menagerist': { kind: 'choice', display: 'radio', archived: true, future: { a: 1 } }
		} as JsonSchemaProperty;
		expect(propertyFromField(fieldFromProperty('format', prop, false))).toEqual(prop);
	});

	it('writes the kind for a new field with no prior metadata', () => {
		const field = {
			key: 'n',
			label: 'N',
			kind: 'number',
			required: false,
			options: [],
			subFields: []
		};
		expect(propertyFromField(field)).toEqual({
			title: 'N',
			type: 'number',
			'x-menagerist': { kind: 'number' }
		});
	});
});

describe('example schema contract fixture', () => {
	const fixture = JSON.parse(
		readFileSync(
			fileURLToPath(
				new URL('../../docs/field-types-spec/example-node-type-schema.json', import.meta.url)
			),
			'utf8'
		)
	) as { properties: Record<string, JsonSchemaProperty> };

	for (const [key, prop] of Object.entries(fixture.properties)) {
		it(`round-trips "${key}" unchanged`, () => {
			expect(propertyFromField(fieldFromProperty(key, prop, false))).toEqual(prop);
		});
	}
});
