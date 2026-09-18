import { describe, it, expect } from 'vitest';
import {
	attributesToRows,
	rowsToAttributes,
	type AttributeRow
} from '../src/lib/components/attributes-editor.svelte';

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
