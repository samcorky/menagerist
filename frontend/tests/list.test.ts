import { describe, it, expect } from 'vitest';
import { getDescriptor, fieldFromProperty, propertyFromField } from '../src/lib/field-types';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

describe('list descriptor', () => {
	const listProp: JsonSchemaProperty = {
		title: 'Instructions',
		type: 'array',
		items: { type: 'string' },
		'x-menagerist': { kind: 'list' }
	};

	it('matches only an explicit kind, not a bare array-of-strings shape', () => {
		const noKind: JsonSchemaProperty = { title: 'Tags', type: 'array', items: { type: 'string' } };
		expect(getDescriptor('list')!.fromSchema('tags', noKind, false)).toBeNull();
		expect(getDescriptor('list')!.fromSchema('instructions', listProp, false)).not.toBeNull();
	});

	it('round-trips through the editor field', () => {
		expect(propertyFromField(fieldFromProperty('instructions', listProp, false))).toEqual(listProp);
	});

	it('round-trips the multiline meta flag (a growing textarea per item, not a display option)', () => {
		const multilineProp: JsonSchemaProperty = {
			...listProp,
			'x-menagerist': { kind: 'list', multiline: true }
		};
		const field = fieldFromProperty('instructions', multilineProp, false);
		expect(field.meta?.multiline).toBe(true);
		expect(propertyFromField(field)).toEqual(multilineProp);
	});

	it('has its own EditorExtras for the multiline toggle, separate from displayOptions', () => {
		expect(getDescriptor('list')?.EditorExtras).toBeDefined();
	});

	it('is not offered as a group sub-field', () => {
		expect(getDescriptor('list')?.canBeSubField).toBe(false);
	});

	it('is not highlightable', () => {
		expect(getDescriptor('list')?.highlightable).not.toBe(true);
	});

	it('defaults to numbered display', () => {
		expect(getDescriptor('list')?.displayOptions?.[0].default).toBe('numbered');
	});
});
