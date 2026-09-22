import { describe, it, expect } from 'vitest';
import { quantityText } from '../src/lib/field-types/quantity/format';
import { getDescriptor, fieldFromProperty, propertyFromField } from '../src/lib/field-types';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

describe('quantityText', () => {
	it('joins value and unit with a space', () => {
		expect(quantityText({ value: 180, unit: 'g' })).toBe('180 g');
	});

	it('shows just the value or just the unit when the other is missing', () => {
		expect(quantityText({ value: 180 })).toBe('180');
		expect(quantityText({ unit: 'g' })).toBe('g');
	});

	it('returns an empty string for no value, non-object, or empty unit', () => {
		expect(quantityText({})).toBe('');
		expect(quantityText(undefined)).toBe('');
		expect(quantityText('180 g')).toBe('');
		expect(quantityText({ value: 180, unit: '' })).toBe('180');
	});
});

describe('quantity descriptor', () => {
	const quantityProp = {
		title: 'Weight',
		type: 'object',
		properties: {
			value: { title: 'Value', type: 'number' },
			unit: { title: 'Unit', type: 'string' }
		},
		'x-menagerist': { kind: 'quantity' }
	} as JsonSchemaProperty;

	it('is registered and matched only by its explicit kind', () => {
		expect(getDescriptor('quantity')).toBeDefined();
		expect(fieldFromProperty('weight', quantityProp, false).kind).toBe('quantity');

		const plainObject = {
			title: 'Weight',
			type: 'object',
			properties: quantityProp.type === 'object' ? quantityProp.properties : {}
		} as JsonSchemaProperty;
		expect(fieldFromProperty('weight', plainObject, false).kind).toBe('opaque');
	});

	it('round-trips through the editor field', () => {
		expect(propertyFromField(fieldFromProperty('weight', quantityProp, false))).toEqual(
			quantityProp
		);
	});

	it('is not offered as a group sub-field in v1', () => {
		expect(getDescriptor('quantity')?.canBeSubField).toBe(false);
	});

	it('formatSummary renders "{value} {unit}" or null when empty', () => {
		const desc = getDescriptor('quantity')!;
		expect(desc.formatSummary?.({ value: 180, unit: 'g' }, quantityProp)).toBe('180 g');
		expect(desc.formatSummary?.({}, quantityProp)).toBeNull();
	});

	it('writes the constrained object shape for a new field', () => {
		const field = {
			key: 'weight',
			label: 'Weight',
			kind: 'quantity',
			required: false,
			options: [],
			subFields: []
		};
		expect(propertyFromField(field)).toEqual(quantityProp);
	});
});
