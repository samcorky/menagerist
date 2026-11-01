import { describe, it, expect } from 'vitest';
import { Validator } from '@cfworker/json-schema';
import {
	getDescriptor,
	descriptorForProp,
	fieldFromProperty,
	propertyFromField
} from '../src/lib/field-types';
import { PARTIAL_DATE_PATTERN } from '../src/lib/field-types/partialdate/partialdate';
import { allowedKinds } from '../src/lib/field-types/kind-changes';
import { formatPartialDate } from '../src/lib/format-date';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

describe('partialdate', () => {
	const prop = {
		title: 'Released',
		type: 'string',
		pattern: PARTIAL_DATE_PATTERN,
		'x-menagerist': { kind: 'partialdate' }
	} as JsonSchemaProperty;

	it('is matched by its exact pattern, ahead of text', () => {
		expect(descriptorForProp(prop)?.kind).toBe('partialdate');
		const { 'x-menagerist': _meta, ...bare } = prop;
		expect(descriptorForProp(bare as JsonSchemaProperty)?.kind).toBe('partialdate');
	});

	it('does not claim other patterns, a phone pattern or a date format', () => {
		const d = getDescriptor('partialdate')!;
		expect(
			d.fromSchema(
				'a',
				{ title: 'A', type: 'string', pattern: '^[A-Z]{3}$' } as JsonSchemaProperty,
				false
			)
		).toBeNull();
		expect(d.fromSchema('a', { title: 'A', type: 'string', format: 'date' }, false)).toBeNull();
	});

	it('round-trips through the editor field', () => {
		expect(propertyFromField(fieldFromProperty('released', prop, false))).toEqual(prop);
	});

	it('accepts a year, a year and month, or a full date, and nothing else', () => {
		const validator = new Validator({ type: 'string', pattern: PARTIAL_DATE_PATTERN });
		for (const ok of ['1973', '1973-03', '1973-03-14', '1973-12-31']) {
			expect(validator.validate(ok).valid, ok).toBe(true);
		}
		for (const bad of [
			'',
			'73',
			'1973-3',
			'1973-13',
			'1973-00',
			'1973-03-32',
			'1973-03-00',
			'1973-03-14x',
			'١٩٧٣'
		]) {
			expect(validator.validate(bad).valid, bad).toBe(false);
		}
	});

	it('gives a friendly pattern error', () => {
		const d = getDescriptor('partialdate')!;
		expect(d.formatError?.('pattern', 'x')).toMatch(/1973-03-14/);
		expect(d.formatError?.('type', 'x')).toBeNull();
	});

	it('formats at the precision entered', () => {
		expect(formatPartialDate('1973', 'short')).toBe('1973');
		expect(formatPartialDate('1973-03', 'long')).toMatch(/1973/);
		expect(formatPartialDate('1973-03', 'long')).not.toMatch(/\b14\b/);
		expect(formatPartialDate('1973-03-14', 'short')).toMatch(/14/);
		expect(formatPartialDate('nonsense', 'short')).toBe('nonsense');
	});

	it('lets a date loosen to a partial date but not the reverse', () => {
		const all = ['date', 'partialdate', 'text', 'number'];
		expect(allowedKinds('date', all)).toEqual(['date', 'partialdate', 'text']);
		expect(allowedKinds('partialdate', all)).toEqual(['partialdate', 'text']);
	});

	it('is a sub-field and highlightable', () => {
		const d = getDescriptor('partialdate')!;
		expect(d.canBeSubField).toBe(true);
		expect(d.highlightable).toBe(true);
	});
});
