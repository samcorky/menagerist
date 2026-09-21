import { describe, it, expect } from 'vitest';
import {
	attributesToRows,
	newDetailRow,
	rowsToAttributes,
	type AttributeRow
} from '../src/lib/attribute-rows';
import {
	MAX_CUSTOM_DETAILS,
	MAX_CUSTOM_NAME_LENGTH,
	canAddDetail,
	customDetailProblems,
	displayDetailValue,
	isDetailRow
} from '../src/lib/custom-details';
import type { AttributesSchema } from '../src/lib/schema-types';

const schema = {
	$schema: 'https://json-schema.org/draft/2020-12/schema',
	type: 'object',
	properties: {
		region: { title: 'Region', type: 'string' },
		old_note: {
			title: 'Old note',
			type: 'string',
			'x-menagerist': { kind: 'text', archived: true }
		},
		year: { title: 'Year', type: 'number' }
	}
} as unknown as AttributesSchema;

function row(key: string, value = 'x', extra: Partial<AttributeRow> = {}): AttributeRow {
	return { key, value, ...extra };
}

describe('lossless round trip', () => {
	it('keeps numbers, booleans, null, objects and lists as stored', () => {
		const stored = {
			count: 5,
			ratio: 12.5,
			seen: true,
			off: false,
			nothing: null,
			nested: { a: 1, b: ['x', 2] },
			tags: ['a', 'b'],
			numbers: [1, 2],
			empty: {},
			text: 'hello'
		};
		expect(rowsToAttributes(attributesToRows(stored))).toEqual(stored);
	});

	it('keeps a type after editing another field', () => {
		const rows = attributesToRows({ count: 5, name: 'a' });
		const edited = rows.map((r) => (r.key === 'name' ? { ...r, value: 'b' } : r));
		expect(rowsToAttributes(edited)).toEqual({ count: 5, name: 'b' });
	});

	it('shows unedited values read-only as compact JSON', () => {
		const rows = attributesToRows({ nothing: null, nested: { a: [1] } });
		expect(rows.map(displayDetailValue)).toEqual(['{"a":[1]}', 'null']);
	});

	it('shows yes/no in words and numbers as typed', () => {
		const rows = attributesToRows({ a: true, b: false, c: 7 });
		expect(rows.map(displayDetailValue)).toEqual(['Yes', 'No', '7']);
	});

	it('writes edited numbers and yes/no back with their type', () => {
		const rows = attributesToRows({ count: 5, seen: false }).map((r) =>
			r.key === 'count' ? { ...r, value: '6' } : r.key === 'seen' ? { ...r, value: 'true' } : r
		);
		expect(rowsToAttributes(rows)).toEqual({ count: 6, seen: true });
	});

	it('omits a cleared number detail', () => {
		const rows = attributesToRows({ count: 5 }).map((r) => ({ ...r, value: '' }));
		expect(rowsToAttributes(rows)).toEqual({});
	});

	it('does not stringify a schema field either', () => {
		const rows = attributesToRows({ year: 1979, region: 'EU' });
		expect(rowsToAttributes(rows, schema)).toEqual({ year: 1979, region: 'EU' });
	});
});

describe('ordering and names', () => {
	it('orders rows by name, ignoring case, so reloads are stable', () => {
		const rows = attributesToRows({ zeta: 1, Region: 1, 'a-long-custom-name': 1, aa: 1, k1: 1 });
		expect(rows.map((r) => r.key)).toEqual(['a-long-custom-name', 'aa', 'k1', 'Region', 'zeta']);
	});

	it('trims names on the way out', () => {
		expect(rowsToAttributes([row('  Region  ', 'EU')])).toEqual({ Region: 'EU' });
	});

	it('drops a blank-named row', () => {
		expect(rowsToAttributes([row('  ', 'EU')])).toEqual({});
	});
});

describe('new detail rows', () => {
	it('start empty, typed and marked as details', () => {
		expect(newDetailRow()).toEqual({ key: '', value: '', kind: 'text', extra: true });
		expect(newDetailRow('boolean')).toEqual({
			key: '',
			value: 'false',
			kind: 'boolean',
			extra: true
		});
		expect(newDetailRow('number').kind).toBe('number');
	});

	it('are written with their own type', () => {
		const number = { ...newDetailRow('number'), key: 'Weight', value: '2.5' };
		const flag = { ...newDetailRow('boolean'), key: 'Signed', value: 'true' };
		const text = { ...newDetailRow('text'), key: 'Note', value: 'hi' };
		expect(rowsToAttributes([number, flag, text])).toEqual({
			Weight: 2.5,
			Signed: true,
			Note: 'hi'
		});
	});
});

describe('isDetailRow', () => {
	it('is true for keys the schema does not define, or rows added as details', () => {
		expect(isDetailRow(row('Region'), schema)).toBe(true);
		expect(isDetailRow(row('Region'), null)).toBe(true);
		expect(isDetailRow(row('region'), schema)).toBe(false);
		expect(isDetailRow(row('old_note'), schema)).toBe(false);
		expect(isDetailRow(row('region', 'x', { extra: true }), schema)).toBe(true);
		expect(isDetailRow(row('constructor'), schema)).toBe(true);
	});
});

describe('customDetailProblems', () => {
	it('has no problems for ordinary details', () => {
		const result = customDetailProblems([row('Colour'), row('Size'), row('region')], schema);
		expect(result.blocking).toBe(false);
		expect(result.errors.size).toBe(0);
	});

	it('flags a named value with no name, but not an untouched row', () => {
		const blank = row('  ', 'value');
		const untouched = newDetailRow();
		const flag = newDetailRow('boolean');
		const result = customDetailProblems([blank, untouched, flag], schema);
		expect([...result.errors.values()]).toEqual(['Give this detail a name.']);
		expect(result.errors.has(blank)).toBe(true);
		expect(result.blocking).toBe(true);
	});

	it('flags duplicate names, ignoring case and spaces, on every row involved', () => {
		const a = row('Region');
		const b = row(' region ');
		const other = row('Other');
		const result = customDetailProblems([a, b, other], null);
		expect(result.errors.get(a)).toBe('This name is already in use.');
		expect(result.errors.get(b)).toBe('This name is already in use.');
		expect(result.errors.has(other)).toBe(false);
	});

	it('flags a name that matches a field, including a removed one, ignoring case', () => {
		const clash = row('Region', 'x', { extra: true });
		const removed = row('OLD_NOTE', 'x', { extra: true });
		const result = customDetailProblems([clash, removed], schema);
		expect(result.errors.get(clash)).toBe('This name is already in use.');
		expect(result.errors.get(removed)).toBe('This name is already in use.');
	});

	it('does not flag a field row as a duplicate of itself', () => {
		expect(customDetailProblems([row('region', 'EU')], schema).blocking).toBe(false);
	});

	it('limits the length of a new name but not one that was already stored', () => {
		const long = 'x'.repeat(MAX_CUSTOM_NAME_LENGTH + 1);
		const added = row(long, 'x', { extra: true });
		const stored = row(long);
		expect(customDetailProblems([added], null).errors.get(added)).toBe(
			`Names can be at most ${MAX_CUSTOM_NAME_LENGTH} characters.`
		);
		expect(customDetailProblems([stored], null).blocking).toBe(false);
		expect(
			customDetailProblems([row('x'.repeat(MAX_CUSTOM_NAME_LENGTH), 'x', { extra: true })], null)
				.blocking
		).toBe(false);
	});
});

describe('canAddDetail', () => {
	it('stops at the limit and does not count fields', () => {
		const details = Array.from({ length: MAX_CUSTOM_DETAILS }, (_, i) => row(`d${i}`));
		expect(canAddDetail(details.slice(1), schema)).toBe(true);
		expect(canAddDetail(details, schema)).toBe(false);
		expect(canAddDetail([...details.slice(1), row('region')], schema)).toBe(true);
	});
});
