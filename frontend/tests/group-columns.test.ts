import { describe, it, expect } from 'vitest';
import { orderedColumns } from '../src/lib/field-types/group/columns';
import { getDescriptor } from '../src/lib/field-types';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

const groupProp = (
	properties: Record<string, JsonSchemaProperty>,
	columns?: string[]
): JsonSchemaProperty =>
	({
		title: 'Cast',
		type: 'array',
		items: { type: 'object', properties },
		...(columns ? { 'x-menagerist': { columns } } : {})
	}) as JsonSchemaProperty;

describe('orderedColumns', () => {
	const properties = {
		zeta_field: { title: 'Zeta', type: 'string' },
		aa: { title: 'Aa', type: 'string' },
		region: { title: 'Region', type: 'string' }
	} as Record<string, JsonSchemaProperty>;

	it('returns [] for a non-array property', () => {
		expect(orderedColumns({ title: 'X', type: 'string' })).toEqual([]);
	});

	it('falls back to object key order when there is no explicit column list', () => {
		expect(orderedColumns(groupProp(properties)).map(([k]) => k)).toEqual(Object.keys(properties));
	});

	it('uses the explicit column order over object key order', () => {
		const prop = groupProp(properties, ['region', 'zeta_field', 'aa']);
		expect(orderedColumns(prop).map(([k]) => k)).toEqual(['region', 'zeta_field', 'aa']);
	});

	it('appends a property missing from the saved column list at the end', () => {
		const prop = groupProp(properties, ['region']);
		expect(orderedColumns(prop).map(([k]) => k)).toEqual(['region', 'zeta_field', 'aa']);
	});

	it('drops a saved column key that no longer has a property', () => {
		const prop = groupProp(properties, ['gone', 'region', 'aa', 'zeta_field']);
		expect(orderedColumns(prop).map(([k]) => k)).toEqual(['region', 'aa', 'zeta_field']);
	});
});

describe('group toSchema/fromSchema column order', () => {
	it('writes an explicit column order that survives object-key reordering', () => {
		const desc = getDescriptor('group')!;
		const field = {
			key: 'cast',
			label: 'Cast',
			kind: 'group',
			required: false,
			options: [],
			subFields: [
				{ key: 'zeta_field', label: 'Zeta', kind: 'text' },
				{ key: 'aa', label: 'Aa', kind: 'text' },
				{ key: 'region', label: 'Region', kind: 'text' }
			]
		};

		const prop = desc.toSchema(field);
		expect(prop.type === 'array' && prop['x-menagerist']?.columns).toEqual([
			'zeta_field',
			'aa',
			'region'
		]);

		// Simulate the JSONB key reordering a save/reload round trip can introduce.
		if (prop.type !== 'array' || prop.items.type !== 'object') {
			throw new Error('expected an array-of-objects property');
		}
		const reordered = {
			...prop,
			items: {
				...prop.items,
				properties: Object.fromEntries(
					Object.entries(prop.items.properties).sort(([a], [b]) => a.localeCompare(b))
				)
			}
		};

		const back = desc.fromSchema('cast', reordered, false)!;
		expect(back.subFields.map((sf) => sf.key)).toEqual(['zeta_field', 'aa', 'region']);
	});
});
