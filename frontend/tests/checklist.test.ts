import { describe, it, expect } from 'vitest';
import { getDescriptor, fieldFromProperty, propertyFromField } from '../src/lib/field-types';
import { checklistCount } from '../src/lib/field-types/checklist/format';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

describe('checklist descriptor', () => {
	const checklistProp: JsonSchemaProperty = {
		title: 'Packing list',
		type: 'array',
		items: {
			type: 'object',
			properties: {
				text: { title: 'Text', type: 'string' },
				done: { title: 'Done', type: 'boolean' }
			}
		},
		'x-menagerist': { kind: 'checklist' }
	};

	it('matches only an explicit kind, not a bare array-of-objects shape (that is `group`)', () => {
		const noKind: JsonSchemaProperty = {
			title: 'Cast',
			type: 'array',
			items: { type: 'object', properties: { name: { title: 'Name', type: 'string' } } }
		};
		expect(getDescriptor('checklist')!.fromSchema('cast', noKind, false)).toBeNull();
		expect(
			getDescriptor('checklist')!.fromSchema('packing_list', checklistProp, false)
		).not.toBeNull();
	});

	it('round-trips through the editor field', () => {
		expect(propertyFromField(fieldFromProperty('packing_list', checklistProp, false))).toEqual(
			checklistProp
		);
	});

	it('is not offered as a group sub-field', () => {
		expect(getDescriptor('checklist')?.canBeSubField).toBe(false);
	});

	it('is highlightable, summarised as "checked/total"', () => {
		const desc = getDescriptor('checklist')!;
		expect(desc.highlightable).toBe(true);
		expect(
			desc.formatSummary?.([{ text: 'Passport', done: true }, { text: 'Charger' }], checklistProp)
		).toBe('1/2');
	});

	it('formatSummary returns null for an empty or non-array value', () => {
		const desc = getDescriptor('checklist')!;
		expect(desc.formatSummary?.([], checklistProp)).toBeNull();
		expect(desc.formatSummary?.(undefined, checklistProp)).toBeNull();
	});
});

describe('checklistCount', () => {
	it('counts done rows against the total', () => {
		expect(
			checklistCount([
				{ text: 'a', done: true },
				{ text: 'b', done: false }
			])
		).toEqual({
			checked: 1,
			total: 2
		});
		expect(checklistCount([{ text: 'a' }])).toEqual({ checked: 0, total: 1 });
	});

	it('returns null for an empty array or a non-array value', () => {
		expect(checklistCount([])).toBeNull();
		expect(checklistCount(undefined)).toBeNull();
		expect(checklistCount('not an array')).toBeNull();
	});
});
