import { describe, it, expect } from 'vitest';
import {
	attributesToRows,
	rowsToAttributes,
	type AttributeRow
} from '../src/lib/components/attributes-editor.svelte';
import type { AttributesSchema } from '../src/lib/components/schema-editor.svelte';

const schema = (properties: AttributesSchema['properties']): AttributesSchema => ({
	$schema: 'https://json-schema.org/draft/2020-12/schema',
	type: 'object',
	properties
});

describe('attributesToRows', () => {
	it('converts scalar attributes to string-valued rows', () => {
		expect(attributesToRows({ colour: 'red', count: 3, active: true })).toEqual([
			{ key: 'colour', value: 'red' },
			{ key: 'count', value: '3' },
			{ key: 'active', value: 'true' }
		]);
	});

	it('converts a repeating group into a row with an array of stringified sub-rows', () => {
		const rows = attributesToRows({
			ingredients: [
				{ name: 'Flour', quantity: 200, unit: 'g' },
				{ name: 'Sugar', quantity: 50, unit: 'g' }
			]
		});

		expect(rows).toEqual([
			{
				key: 'ingredients',
				value: [
					{ name: 'Flour', quantity: '200', unit: 'g' },
					{ name: 'Sugar', quantity: '50', unit: 'g' }
				]
			}
		]);
	});

	it('treats an empty group as an empty array of rows, not a scalar', () => {
		expect(attributesToRows({ ingredients: [] })).toEqual([{ key: 'ingredients', value: [] }]);
	});
});

describe('rowsToAttributes', () => {
	it('drops rows with an empty or whitespace key', () => {
		const rows: AttributeRow[] = [
			{ key: 'colour', value: 'red' },
			{ key: '', value: 'ignored' },
			{ key: '   ', value: 'ignored' }
		];

		expect(rowsToAttributes(rows)).toEqual({ colour: 'red' });
	});

	it('passes group rows through as an array of records', () => {
		const rows: AttributeRow[] = [
			{
				key: 'ingredients',
				value: [{ name: 'Flour', quantity: '200', unit: 'g' }]
			}
		];

		expect(rowsToAttributes(rows)).toEqual({
			ingredients: [{ name: 'Flour', quantity: '200', unit: 'g' }]
		});
	});
});

describe('round-trip', () => {
	it('preserves a repeating group through attributesToRows then rowsToAttributes', () => {
		const original = {
			name: 'Recipe',
			ingredients: [
				{ name: 'Flour', quantity: '200', unit: 'g' },
				{ name: 'Sugar', quantity: '50', unit: 'g' }
			]
		};

		expect(rowsToAttributes(attributesToRows(original))).toEqual(original);
	});
});

describe('rowsToAttributes with schema', () => {
	it('coerces number fields to JS numbers', () => {
		const rows: AttributeRow[] = [{ key: 'year', value: '1979' }];
		const result = rowsToAttributes(rows, schema({ year: { title: 'Year', type: 'number' } }));
		expect(result).toEqual({ year: 1979 });
		expect(typeof result.year).toBe('number');
	});

	it('omits empty number fields rather than sending an empty string', () => {
		const rows: AttributeRow[] = [{ key: 'year', value: '' }];
		expect(rowsToAttributes(rows, schema({ year: { title: 'Year', type: 'number' } }))).toEqual({});
	});

	it('passes non-numeric strings through for number fields (backend validates)', () => {
		const rows: AttributeRow[] = [{ key: 'year', value: 'abc' }];
		expect(rowsToAttributes(rows, schema({ year: { title: 'Year', type: 'number' } }))).toEqual({
			year: 'abc'
		});
	});

	it('coerces boolean fields: "true" → true, "false" → false', () => {
		const rows: AttributeRow[] = [
			{ key: 'owned', value: 'true' },
			{ key: 'sold', value: 'false' }
		];
		expect(
			rowsToAttributes(
				rows,
				schema({
					owned: { title: 'Owned', type: 'boolean' },
					sold: { title: 'Sold', type: 'boolean' }
				})
			)
		).toEqual({ owned: true, sold: false });
	});

	it('coerces numeric sub-fields inside group rows', () => {
		const rows: AttributeRow[] = [{ key: 'prices', value: [{ currency: 'GBP', amount: '12.50' }] }];
		expect(
			rowsToAttributes(
				rows,
				schema({
					prices: {
						title: 'Prices',
						type: 'array',
						items: {
							type: 'object',
							properties: {
								currency: { title: 'Currency', type: 'string' },
								amount: { title: 'Amount', type: 'number' }
							}
						}
					}
				})
			)
		).toEqual({ prices: [{ currency: 'GBP', amount: 12.5 }] });
	});

	it('passes unknown keys through as strings regardless of schema', () => {
		const rows: AttributeRow[] = [{ key: 'notes', value: 'free text' }];
		expect(rowsToAttributes(rows, schema({ year: { title: 'Year', type: 'number' } }))).toEqual({
			notes: 'free text'
		});
	});

	it('round-trips typed values: attributesToRows → rowsToAttributes restores original types', () => {
		const original = { year: 1979, owned: true, title: 'Alien' };
		const s = schema({
			year: { title: 'Year', type: 'number' },
			owned: { title: 'Owned', type: 'boolean' },
			title: { title: 'Title', type: 'string' }
		});
		expect(rowsToAttributes(attributesToRows(original), s)).toEqual(original);
	});
});
