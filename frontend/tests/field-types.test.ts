import { describe, it, expect } from 'vitest';
import { allDescriptors, descriptorForProp, getDescriptor } from '../src/lib/field-types/index';
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
		['longtext', { title: 'Notes', type: 'string', 'x-multiline': true }],
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

	it('does not match longtext prop', () => {
		const ltProp: JsonSchemaProperty = { title: 'X', type: 'string', 'x-multiline': true };
		expect(getDescriptor('text')!.fromSchema('x', ltProp, false)).toBeNull();
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
