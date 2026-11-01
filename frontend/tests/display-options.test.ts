import { describe, it, expect } from 'vitest';
import { getDescriptor, fieldFromProperty, propertyFromField } from '../src/lib/field-types';
import {
	displayChoices,
	displayValue,
	setDisplayValue
} from '../src/lib/field-types/display-options';
import { changeKind } from '../src/lib/field-types/kind-changes';
import type { EditorField, JsonSchemaProperty } from '../src/lib/schema-types';

const field = (kind: string, extra: Partial<EditorField> = {}): EditorField => ({
	key: 'f',
	label: 'F',
	kind,
	required: false,
	options: [],
	subFields: [],
	...extra
});

describe('descriptor displayOptions', () => {
	it('boolean, choice and rating declare their options with defaults', () => {
		const boolean = getDescriptor('boolean')!.displayOptions![0];
		expect(boolean.choices.map((c) => c.value)).toEqual(['switch', 'checkbox', 'yes-no']);
		expect(boolean.default).toBe('switch');
		const choice = getDescriptor('choice')!.displayOptions![0];
		expect(choice.choices.map((c) => c.value)).toEqual(['dropdown', 'radio', 'chips']);
		expect(choice.default).toBe('dropdown');
		const rating = getDescriptor('rating')!.displayOptions![0];
		expect(rating.choices.map((c) => c.value)).toEqual(['3', '5', '10']);
		expect(rating.default).toBe('5');
	});

	it('other kinds declare none', () => {
		expect(getDescriptor('text')!.displayOptions).toBeUndefined();
		expect(getDescriptor('date')!.displayOptions).toBeUndefined();
	});
});

describe('display value helpers', () => {
	const option = getDescriptor('boolean')!.displayOptions![0];

	it('falls back to the default when unset', () => {
		expect(displayValue(field('boolean'), option)).toBe('switch');
	});

	it('stores a non-default choice and removes it again for the default', () => {
		const set = setDisplayValue(field('boolean'), option, 'yes-no');
		expect(set.meta?.display).toBe('yes-no');
		expect(displayValue(set, option)).toBe('yes-no');
		expect(setDisplayValue(set, option, 'switch').meta).not.toHaveProperty('display');
	});

	it('lists a stored value the descriptor does not know about', () => {
		const odd = field('boolean', { meta: { display: 'future' } });
		expect(displayChoices(odd, option).map((c) => c.value)).toContain('future');
	});
});

describe('display round-trips', () => {
	it('keeps the display setting when a schema is read and written back', () => {
		const prop = {
			title: 'Signed?',
			type: 'boolean',
			'x-menagerist': { kind: 'boolean', display: 'yes-no' }
		} as JsonSchemaProperty;
		expect(propertyFromField(fieldFromProperty('signed', prop, false))).toEqual(prop);
	});

	it('changing "Show as" changes only the metadata, not the validation keywords', () => {
		const before = propertyFromField(field('choice', { options: ['A', 'B'] }));
		const after = propertyFromField(
			setDisplayValue(
				field('choice', { options: ['A', 'B'] }),
				getDescriptor('choice')!.displayOptions![0],
				'radio'
			)
		);
		expect({ ...after, 'x-menagerist': undefined }).toEqual({
			...before,
			'x-menagerist': undefined
		});
		expect(after['x-menagerist']?.display).toBe('radio');
	});

	it('a schema without display renders each type with its default', () => {
		const prop: JsonSchemaProperty = { title: 'On', type: 'boolean' };
		const f = fieldFromProperty('on', prop, false);
		expect(displayValue(f, getDescriptor('boolean')!.displayOptions![0])).toBe('switch');
	});
});

describe('rating star count', () => {
	const option = getDescriptor('rating')!.displayOptions![0];
	const ratingProp = (maximum: number) =>
		({
			title: 'Score',
			type: 'number',
			minimum: 1,
			maximum,
			multipleOf: 1,
			'x-menagerist': { kind: 'rating' }
		}) as JsonSchemaProperty;

	it('is read from the maximum and written back to it', () => {
		const f = fieldFromProperty('score', ratingProp(10), false);
		expect(displayValue(f, option)).toBe('10');
		expect(propertyFromField(f)).toEqual(ratingProp(10));
	});

	it('changing it changes only maximum', () => {
		const f = setDisplayValue(fieldFromProperty('score', ratingProp(5), false), option, '3');
		expect(propertyFromField(f)).toEqual(ratingProp(3));
	});

	it('defaults to five stars for a new rating and is dropped when the kind changes', () => {
		expect((propertyFromField(field('rating')) as { maximum: number }).maximum).toBe(5);
		const changed = changeKind(setDisplayValue(field('rating'), option, '10'), 'number');
		expect(changed.config).toBeUndefined();
	});
});
