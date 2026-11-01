import { describe, it, expect } from 'vitest';
import { Validator } from '@cfworker/json-schema';
import {
	getDescriptor,
	descriptorForProp,
	fieldFromProperty,
	propertyFromField
} from '../src/lib/field-types';
import {
	durationSeconds,
	formatDuration,
	parseDuration
} from '../src/lib/field-types/duration/format';
import { allowedKinds, kindChangeWarning } from '../src/lib/field-types/kind-changes';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

describe('parseDuration', () => {
	it.each([
		['3:45', 225],
		['03:05', 185],
		['1:02:03', 3723],
		['75:30', 4530],
		['0:00', 0],
		['90', 90],
		[' 3:45 ', 225],
		['1h 2m 3s', 3723],
		['1h', 3600],
		['2m30s', 150],
		['45S', 45]
	])('reads %j as %d seconds', (text, seconds) => {
		expect(parseDuration(text)).toBe(seconds);
	});

	it.each(['', '  ', 'abc', '3:60', '1:75:00', '1:2:3:4', '-5', '1.5', '3:', ':45', 'h', '1x'])(
		'rejects %j',
		(text) => {
			expect(parseDuration(text)).toBeNull();
		}
	);
});

describe('formatDuration', () => {
	it('formats as a clock', () => {
		expect(formatDuration(225)).toBe('3:45');
		expect(formatDuration(5)).toBe('0:05');
		expect(formatDuration(3723)).toBe('1:02:03');
		expect(formatDuration(0)).toBe('0:00');
	});

	it('formats as words, dropping zero parts', () => {
		expect(formatDuration(3723, 'words')).toBe('1h 2m 3s');
		expect(formatDuration(3600, 'words')).toBe('1h');
		expect(formatDuration(0, 'words')).toBe('0s');
	});

	it('round-trips through parse', () => {
		for (const n of [0, 1, 59, 60, 225, 3599, 3600, 86399, 100000]) {
			expect(parseDuration(formatDuration(n))).toBe(n);
			expect(parseDuration(formatDuration(n, 'words'))).toBe(n);
		}
	});
});

describe('durationSeconds', () => {
	it('accepts non-negative finite numbers and digit strings, as forms hand them over', () => {
		expect(durationSeconds(225)).toBe(225);
		expect(durationSeconds(0)).toBe(0);
		expect(durationSeconds('225')).toBe(225);
		for (const v of [-1, NaN, Infinity, '3:45', '-5', '1.5', '', null, undefined]) {
			expect(durationSeconds(v)).toBeNull();
		}
	});
});

describe('duration descriptor', () => {
	const prop = {
		title: 'Length',
		type: 'number',
		minimum: 0,
		multipleOf: 1,
		'x-menagerist': { kind: 'duration' }
	} as JsonSchemaProperty;

	it('only matches an explicit kind, never a plain number', () => {
		expect(descriptorForProp(prop)?.kind).toBe('duration');
		expect(descriptorForProp({ title: 'N', type: 'number' })?.kind).toBe('number');
		expect(
			getDescriptor('duration')!.fromSchema('n', { title: 'N', type: 'number' }, false)
		).toBeNull();
	});

	it('round-trips through the editor field', () => {
		expect(propertyFromField(fieldFromProperty('length', prop, false))).toEqual(prop);
	});

	it('is a sub-field, highlightable and offers clock or words', () => {
		const d = getDescriptor('duration')!;
		expect(d.canBeSubField).toBe(true);
		expect(d.highlightable).toBe(true);
		expect(d.displayOptions?.[0].default).toBe('clock');
	});

	it('summarises in the chosen style', () => {
		const d = getDescriptor('duration')!;
		expect(d.formatSummary?.(3723, prop)).toBe('1:02:03');
		expect(
			d.formatSummary?.(3723, { ...prop, 'x-menagerist': { kind: 'duration', display: 'words' } })
		).toBe('1h 2m 3s');
		expect(d.formatSummary?.('225', prop)).toBe('3:45');
		expect(d.formatSummary?.('x', prop)).toBeNull();
	});

	it('rejects negative, fractional and non-numeric values', () => {
		const v = new Validator({ type: 'number', minimum: 0, multipleOf: 1 });
		expect(v.validate(225).valid).toBe(true);
		expect(v.validate(-1).valid).toBe(false);
		expect(v.validate(1.5).valid).toBe(false);
		expect(v.validate('3:45').valid).toBe(false);
	});

	it('words its validation errors', () => {
		const d = getDescriptor('duration')!;
		expect(d.formatError?.('type', 'abc')).toMatch(/3:45/);
		expect(d.formatError?.('required', undefined)).toBeNull();
	});

	it('moves between number and duration, with a warning one way', () => {
		const all = ['number', 'duration', 'rating', 'text', 'date'];
		expect(allowedKinds('number', all)).toContain('duration');
		expect(allowedKinds('duration', all)).toEqual(['number', 'duration', 'text']);
		expect(kindChangeWarning('number', 'duration')).toMatch(/negative/);
		expect(kindChangeWarning('duration', 'number')).toBeNull();
	});
});
