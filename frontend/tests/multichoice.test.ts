import { describe, it, expect } from 'vitest';
import {
	getDescriptor,
	descriptorForProp,
	fieldFromProperty,
	propertyFromField
} from '../src/lib/field-types';
import { allowedKinds } from '../src/lib/field-types/kind-changes';
import { attributesToRows, rowsToAttributes } from '../src/lib/attribute-rows';
import type { AttributesSchema, JsonSchemaProperty } from '../src/lib/schema-types';

describe('multichoice descriptor', () => {
	const prop: JsonSchemaProperty = {
		title: 'Formats',
		type: 'array',
		items: { type: 'string', enum: ['CD', 'Vinyl', 'Tape'] },
		uniqueItems: true,
		'x-menagerist': { kind: 'multichoice' }
	};

	it('round-trips through the editor field', () => {
		const field = fieldFromProperty('formats', prop, false);
		expect(field.kind).toBe('multichoice');
		expect(field.options).toEqual(['CD', 'Vinyl', 'Tape']);
		expect(propertyFromField(field)).toEqual(prop);
	});

	it('is inferred from shape when no kind is stored', () => {
		const { 'x-menagerist': _meta, ...bare } = prop;
		expect(descriptorForProp(bare as JsonSchemaProperty)?.kind).toBe('multichoice');
	});

	it('does not claim a plain string list or a table', () => {
		const d = getDescriptor('multichoice')!;
		expect(
			d.fromSchema('a', { title: 'A', type: 'array', items: { type: 'string' } }, false)
		).toBeNull();
		expect(
			d.fromSchema(
				'a',
				{ title: 'A', type: 'array', items: { type: 'object', properties: {} } },
				false
			)
		).toBeNull();
	});

	it('leaves list and group unaffected by its registration', () => {
		const list: JsonSchemaProperty = {
			title: 'L',
			type: 'array',
			items: { type: 'string' },
			'x-menagerist': { kind: 'list' }
		};
		expect(descriptorForProp(list)?.kind).toBe('list');
		const group: JsonSchemaProperty = {
			title: 'G',
			type: 'array',
			items: { type: 'object', properties: {} }
		};
		expect(descriptorForProp(group)?.kind).toBe('group');
	});

	it('is not a sub-field, is highlightable and offers chips or checkboxes', () => {
		const d = getDescriptor('multichoice')!;
		expect(d.canBeSubField).toBe(false);
		expect(d.highlightable).toBe(true);
		expect(d.displayOptions?.[0].default).toBe('chips');
	});

	it('summarises as a comma-separated list, or null when empty', () => {
		const d = getDescriptor('multichoice')!;
		expect(d.formatSummary?.(['CD', 'Tape'], prop)).toBe('CD, Tape');
		expect(d.formatSummary?.([], prop)).toBeNull();
		expect(d.formatSummary?.(undefined, prop)).toBeNull();
	});

	it('can only stay multichoice once saved', () => {
		expect(allowedKinds('multichoice', ['multichoice', 'text', 'list'])).toEqual(['multichoice']);
	});

	it('stores the selection as a string array and omits the key when empty', () => {
		const schema: AttributesSchema = {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties: { formats: prop }
		};
		const rows = attributesToRows({ formats: ['CD', 'Tape'] }, schema);
		expect(rowsToAttributes(rows, schema)).toEqual({ formats: ['CD', 'Tape'] });
		expect(rowsToAttributes([{ key: 'formats', value: [] }], schema)).toEqual({});
	});
});
