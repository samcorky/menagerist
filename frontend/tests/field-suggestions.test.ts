import { describe, expect, it } from 'vitest';
import { fieldNameSuggestions, matchItemField } from '$lib/field-suggestions';
import type { ItemField } from '$lib/item-fields';

const fields: ItemField[] = [
	{ key: 'signed', kind: 'boolean', label: 'Signed', count: 12 },
	{ key: 'paper', kind: 'text', label: 'Paper', count: 4 },
	{ key: 'grade', kind: 'rating', label: 'Grade', count: 9 },
	{ key: 'signed_2', kind: 'text', label: 'Signed', count: 2 }
];

describe('fieldNameSuggestions', () => {
	it('offers each name once, most used first', () => {
		expect(fieldNameSuggestions(fields)).toEqual(['Signed', 'Grade', 'Paper']);
	});

	it('leaves out kinds that cannot be chosen there', () => {
		expect(fieldNameSuggestions(fields, ['text', 'boolean'])).toEqual(['Signed', 'Paper']);
	});
});

describe('matchItemField', () => {
	it('finds the field a name belongs to, ignoring case and spaces at the ends', () => {
		expect(matchItemField(' paper ', fields)?.key).toBe('paper');
	});

	it('picks the most used field when two share a name', () => {
		expect(matchItemField('Signed', fields)?.key).toBe('signed');
	});

	it('only matches kinds that can be chosen there', () => {
		expect(matchItemField('Grade', fields, ['text'])).toBeUndefined();
		expect(matchItemField('Signed', fields, ['text'])?.key).toBe('signed_2');
	});

	it('matches nothing for a new name or an empty one', () => {
		expect(matchItemField('Edition', fields)).toBeUndefined();
		expect(matchItemField('  ', fields)).toBeUndefined();
	});
});
