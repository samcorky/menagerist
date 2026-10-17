import { describe, expect, it } from 'vitest';
import {
	applyDraft,
	chipModels,
	conditionFor,
	conditionProblem,
	fieldOf,
	fieldStatus,
	isBlank,
	itemFieldSubject,
	missingFieldMessage,
	parseItemFieldSubject,
	subjectOf,
	withOperator,
	withSubject
} from '$lib/query/builder';
import { decodeQuery, encodeQuery } from '$lib/query/codec';
import {
	buildCatalogue,
	findItemField,
	ITEM_FIELDS_CAP,
	itemFieldGroup,
	summaryLookup,
	type Catalogue
} from '$lib/query/fields';
import { describeCondition } from '$lib/query/summary';
import type { Condition, Query } from '$lib/query/types';
import { itemTypes } from './query-builder-fixtures';

const itemFields = [
	{ key: 'signed', kind: 'boolean', label: 'Signed', count: 4 },
	{ key: 'size', kind: 'number', label: 'Size', count: 2 },
	{ key: 'size', kind: 'text', label: 'Size', count: 1 },
	{ key: 'rating', kind: 'rating', label: 'Stars', count: 9 }
];
const catalogue: Catalogue = buildCatalogue(itemTypes, true, itemFields);

const signed: Condition = {
	kind: 'field',
	field_kind: 'boolean',
	key: 'signed',
	op: '=',
	value: true
};
const wrap = (...children: Condition[]): Query => ({
	v: 1,
	where: { op: 'and', children },
	sort: []
});
const roundTrip = (c: Condition) => decodeQuery(encodeQuery(wrap(c)));

describe('decoder', () => {
	it('accepts a per-item condition and keeps it as sent', () => {
		expect(roundTrip(signed)).toEqual(wrap(signed));
	});

	it('treats a null type as absent', () => {
		const raw = { ...signed, type: null } as unknown as Condition;
		expect(roundTrip(raw)).toEqual(wrap(signed));
	});

	it.each([
		['both type and field_kind', { ...signed, type: 'film' }],
		['field_kind that is not text', { ...signed, field_kind: 3 }],
		['an empty field_kind', { ...signed, field_kind: '' }],
		['an unknown field_kind', { ...signed, field_kind: 'hologram' }],
		['an inherited field_kind name', { ...signed, field_kind: 'toString' }],
		['a sub_key', { ...signed, sub_key: 'role' }],
		['a reference operand', { ...signed, key: 'a', op: '=', value: { ref: 'b' } }],
		['a reference in a list', { ...signed, op: 'in', value: ['x', { ref: 'b' }] }]
	])('rejects %s', (_name, condition) => {
		expect(roundTrip(condition as unknown as Condition)).toBeNull();
	});

	it('rejects neither type nor field_kind', () => {
		const { field_kind: _kind, ...rest } = signed;
		expect(roundTrip(rest as Condition)).toBeNull();
	});

	it('accepts a null sub_key', () => {
		expect(roundTrip({ ...signed, sub_key: null } as unknown as Condition)).toEqual(wrap(signed));
	});
});

describe('subjects', () => {
	it('names a per-item field item:<kind>:<key>', () => {
		expect(itemFieldSubject('boolean', 'signed')).toBe('item:boolean:signed');
		expect(subjectOf(signed)).toBe('item:boolean:signed');
	});

	it('round-trips keys that contain colons', () => {
		expect(parseItemFieldSubject(itemFieldSubject('text', 'a:b'))).toEqual({
			kind: 'text',
			key: 'a:b'
		});
	});

	it.each(['field:["film","k",null]', 'item:boolean', 'item::k', 'blank'])(
		'does not parse %s',
		(subject) => {
			expect(parseItemFieldSubject(subject)).toBeNull();
		}
	);
});

describe('itemFieldGroup', () => {
	it('offers a Per-item fields group with one option per key and kind', () => {
		const group = itemFieldGroup(catalogue);
		expect(group?.label).toBe('Per-item fields');
		expect(group?.options.map((o) => o.value)).toEqual([
			'item:boolean:signed',
			'item:number:size',
			'item:text:size',
			'item:rating:rating'
		]);
		expect(group?.options[0]).toMatchObject({ label: 'Signed', kind: 'boolean', count: 4 });
	});

	it('is null before the listing loads and when it is empty', () => {
		expect(itemFieldGroup(buildCatalogue(itemTypes))).toBeNull();
		expect(itemFieldGroup(buildCatalogue(itemTypes, true, []))).toBeNull();
	});

	it('leaves out a kind that has no operators', () => {
		const odd = buildCatalogue(itemTypes, true, [
			{ key: 'x', kind: 'group', label: 'X', count: 1 }
		]);
		expect(itemFieldGroup(odd)).toBeNull();
	});

	it('finds a field by kind and key', () => {
		expect(findItemField(catalogue, 'number', 'size')?.count).toBe(2);
		expect(findItemField(catalogue, 'text', 'size')?.count).toBe(1);
		expect(findItemField(catalogue, 'boolean', 'size')).toBeUndefined();
	});
});

describe('building rows', () => {
	it('starts a per-item row on the first operator for its kind, with no value', () => {
		expect(conditionFor('item:boolean:signed', catalogue)).toEqual({
			kind: 'field',
			field_kind: 'boolean',
			key: 'signed',
			op: '='
		});
	});

	it('does not start a row for a kind the table lacks', () => {
		expect(isBlank(conditionFor('item:hologram:x', catalogue))).toBe(true);
	});

	it('resets the operator and value when a type field becomes a per-item field', () => {
		const typed: Condition = { kind: 'field', type: 'film', key: 'rating', op: '>=', value: 4 };
		const next = withSubject(typed, 'item:text:size', catalogue);
		expect(next).toEqual({ kind: 'field', field_kind: 'text', key: 'size', op: '=' });
	});

	it('resets when a per-item field becomes a type field, and between per-item kinds', () => {
		const back = withSubject(signed, 'field:["film","rating",null]', catalogue);
		expect(back).toMatchObject({ type: 'film', key: 'rating' });
		expect('field_kind' in back).toBe(false);
		const other = withSubject(signed, 'item:number:size', catalogue);
		expect(other).toEqual({ kind: 'field', field_kind: 'number', key: 'size', op: '=' });
	});

	it('keeps a row on the same subject untouched', () => {
		expect(withSubject(signed, 'item:boolean:signed', catalogue)).toBe(signed);
	});

	it('resolves the kind from the condition, whatever the listing says', () => {
		expect(fieldOf(signed, catalogue)).toMatchObject({ kind: 'boolean', label: 'Signed' });
		const unlisted: Condition = { ...signed, key: 'gone' };
		expect(fieldOf(unlisted, catalogue)).toMatchObject({ kind: 'boolean', label: 'gone' });
	});

	it('changes the operator by shape as for a type field', () => {
		const size: Condition = { kind: 'field', field_kind: 'number', key: 'size', op: '=', value: 3 };
		expect(withOperator(size, 'between', catalogue)).toMatchObject({ value: ['', ''] });
		expect(withOperator(size, 'empty', catalogue)).not.toHaveProperty('value');
	});
});

describe('problems and status', () => {
	it('checks the value against the kind', () => {
		expect(conditionProblem(signed, catalogue)).toBeNull();
		expect(conditionProblem({ ...signed, value: 'yes' }, catalogue)).toBe('Choose yes or no.');
		expect(conditionProblem({ ...signed, op: '>' }, catalogue)).toBe('Choose how to compare.');
	});

	it('keeps a finished per-item row and drops an unfinished one when applying', () => {
		const half: Condition = { kind: 'field', field_kind: 'number', key: 'size', op: '=' };
		expect(applyDraft(wrap(signed, half), catalogue).query).toEqual(wrap(signed));
	});

	it('is ok when the listing has the field', () => {
		expect(fieldStatus(signed, catalogue)).toBe('ok');
	});

	it('is missing when the listing lacks the key and kind', () => {
		expect(fieldStatus({ ...signed, key: 'gone' }, catalogue)).toBe('missing');
		expect(fieldStatus({ ...signed, field_kind: 'text' }, catalogue)).toBe('missing');
	});

	it('is ok when the listing could not be read', () => {
		expect(fieldStatus(signed, buildCatalogue(itemTypes, true, null))).toBe('ok');
	});

	it('is loading before the item types load', () => {
		expect(fieldStatus(signed, buildCatalogue([], false, itemFields))).toBe('loading');
	});

	it('words the missing state for items, not for removed fields', () => {
		expect(missingFieldMessage(signed)).toBe('No item has this field.');
		expect(missingFieldMessage({ kind: 'field', type: 'film', key: 'k', op: '=' })).toBe(
			'This field no longer exists, so nothing matches.'
		);
	});
});

describe('wording', () => {
	const lookup = summaryLookup(catalogue);

	it('describes a per-item condition as Per-item field › label: operator value', () => {
		expect(describeCondition(signed, lookup)).toBe('Per-item field › Signed: is yes');
		const size: Condition = {
			kind: 'field',
			field_kind: 'number',
			key: 'size',
			op: '>=',
			value: 3
		};
		expect(describeCondition(size, lookup)).toBe('Per-item field › Size: is at least 3');
		const none: Condition = { kind: 'field', field_kind: 'number', key: 'size', op: 'empty' };
		expect(describeCondition(none, lookup)).toBe('Per-item field › Size: is empty');
	});

	it('formats a rating like the type fields do', () => {
		const stars: Condition = {
			kind: 'field',
			field_kind: 'rating',
			key: 'rating',
			op: '>=',
			value: 4
		};
		expect(describeCondition(stars, lookup)).toBe('Per-item field › Stars: is at least 4 stars');
	});

	it('words dates as the date conditions do', () => {
		const when: Condition = {
			kind: 'field',
			field_kind: 'date',
			key: 'bought',
			op: '>=',
			value: { rel: '-30d' }
		};
		expect(describeCondition(when, lookup)).toBe('Per-item field › bought: in the last 30 days');
	});

	it('falls back to the key when the label is unknown', () => {
		expect(describeCondition({ ...signed, key: 'gone' }, lookup)).toBe(
			'Per-item field › gone: is yes'
		);
		const bare = { fieldLabel: (_t: string, k: string) => k, typeLabel: (s: string) => s };
		expect(describeCondition(signed, bare)).toBe('Per-item field › signed: is yes');
	});

	it('shows in chips', () => {
		const { chips } = chipModels(wrap(signed), lookup);
		expect(chips[0].text).toBe('Per-item field › Signed: is yes');
	});
});

describe('a listing cut off at the server cap', () => {
	it('does not flag an absent key as missing, since the field may be beyond the cut', () => {
		const full = Array.from({ length: ITEM_FIELDS_CAP }, (_, i) => ({
			key: `f${i}`,
			kind: 'text',
			label: `F${i}`,
			count: 1
		}));
		const gone = { ...signed, key: 'zzz' };
		expect(fieldStatus(gone, buildCatalogue(itemTypes, true, full))).toBe('ok');
		expect(fieldStatus(gone, buildCatalogue(itemTypes, true, full.slice(1)))).toBe('missing');
	});
});
