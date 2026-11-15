import { describe, expect, it } from 'vitest';
import {
	conditionFor,
	fieldOf,
	fieldStatus,
	GONE_SAVED_FIELD_MESSAGE,
	missingFieldMessage,
	savedFieldPickerItems,
	subjectOf
} from '$lib/query/builder';
import {
	anyTypeFields,
	buildCatalogue,
	itemFieldInfo,
	parseSavedFieldSubject,
	savedFieldInfos,
	savedFieldSubject,
	summaryLookup,
	type ItemTypeLike,
	type SavedField
} from '$lib/query/fields';
import { describeCondition } from '$lib/query/summary';
import type { Condition } from '$lib/query/types';
import type { JsonSchemaProperty } from '$lib/schema-types';

const STATUS_ID = '0190c1d2-0000-7000-8000-0000000000a1';
const ACQ_ID = '0190c1d2-0000-7000-8000-0000000000a2';

const status = (title: string): JsonSchemaProperty => ({
	title,
	type: 'string',
	enum: ['Owned', 'Wanted'],
	'x-menagerist': { kind: 'choice' }
});

const types: ItemTypeLike[] = [
	{
		slug: 'film',
		label: 'Film',
		attributes_schema: {
			type: 'object',
			properties: {
				status: status('Status'),
				runtime: { title: 'Runtime', type: 'number' },
				old: { title: 'Old', type: 'number', 'x-menagerist': { archived: true } }
			}
		}
	},
	{
		slug: 'game',
		label: 'Game',
		attributes_schema: {
			type: 'object',
			properties: {
				status: status('Status'),
				old: { title: 'Old', type: 'number', 'x-menagerist': { archived: true } }
			}
		}
	},
	{
		slug: 'book',
		label: 'Book',
		attributes_schema: { type: 'object', properties: { status: status('State') } }
	}
];

const saved: SavedField[] = [
	{ id: STATUS_ID, label: 'Status', property: status('Status') },
	{
		id: ACQ_ID,
		label: 'Acquisition',
		property: {
			title: 'Acquisition',
			type: 'array',
			items: {
				type: 'object',
				properties: {
					date: {
						title: 'Date',
						type: 'string',
						pattern: '^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$',
						'x-menagerist': { kind: 'partialdate' }
					},
					notes: { title: 'Notes', type: 'string', 'x-menagerist': { kind: 'longtext' } }
				}
			},
			'x-menagerist': { kind: 'group' }
		}
	}
];

const own = [{ key: 'mood', kind: 'choice', label: 'Mood', count: 2 }];
const catalogue = buildCatalogue(types, true, own, saved);
const lookup = summaryLookup(catalogue);

describe('Any item type', () => {
	it('lists a field on two or more types, or on items, by its most common title', () => {
		expect(anyTypeFields(catalogue).map((f) => [f.kind, f.key, f.label])).toEqual([
			['choice', 'mood', 'Mood'],
			['choice', 'status', 'Status']
		]);
	});

	it('offers a type field’s options, and typed values only when no type has the field', () => {
		const fromTypes = itemFieldInfo(catalogue, 'choice', 'status');
		expect(fromTypes.prop).toMatchObject({ enum: ['Owned', 'Wanted'] });
		expect(fromTypes.typedChoice).toBe(false);
		expect(itemFieldInfo(catalogue, 'choice', 'mood').typedChoice).toBe(true);
	});

	it('reads as Any item type in a chip', () => {
		const c: Condition = {
			kind: 'field',
			field_kind: 'choice',
			key: 'status',
			op: '=',
			value: 'Wanted'
		};
		expect(describeCondition(c, lookup)).toBe('Any item type › Status: is Wanted');
	});
});

describe('Saved fields', () => {
	it('lists each saved field and its table columns', () => {
		expect(savedFieldInfos(catalogue).map((f) => [f.origin, f.subKey, f.label, f.kind])).toEqual([
			[STATUS_ID, undefined, 'Status', 'choice'],
			[ACQ_ID, 'date', 'Acquisition › Date', 'partialdate'],
			[ACQ_ID, 'notes', 'Acquisition › Notes', 'longtext']
		]);
		expect(savedFieldPickerItems(catalogue)[1]).toMatchObject({
			value: `saved:${ACQ_ID}:date`,
			group: 'Saved fields',
			selectedLabel: 'Saved fields › Acquisition › Date'
		});
	});

	it('round-trips subjects, columns with colons included', () => {
		expect(parseSavedFieldSubject(savedFieldSubject(STATUS_ID))).toEqual({ origin: STATUS_ID });
		expect(parseSavedFieldSubject(savedFieldSubject(ACQ_ID, 'a:b'))).toEqual({
			origin: ACQ_ID,
			subKey: 'a:b'
		});
		expect(parseSavedFieldSubject('item:choice:status')).toBeNull();
		expect(parseSavedFieldSubject('saved:')).toBeNull();
	});

	it('starts a condition with no key and the kind’s first operator', () => {
		const column = conditionFor(`saved:${ACQ_ID}:date`, catalogue);
		expect(column).toMatchObject({ kind: 'field', origin: ACQ_ID, sub_key: 'date' });
		expect(column).not.toHaveProperty('key');
		expect(subjectOf(column)).toBe(`saved:${ACQ_ID}:date`);
		expect(fieldOf(column, catalogue)?.label).toBe('Acquisition › Date');
		expect(conditionFor(`saved:${STATUS_ID}`, catalogue)).toEqual({
			kind: 'field',
			origin: STATUS_ID,
			op: '='
		});
		expect(conditionFor('saved:unknown', catalogue)).toMatchObject({ type: '', key: '' });
	});

	it('reads as Saved field in a chip, dates like the date conditions', () => {
		const wanted: Condition = { kind: 'field', origin: STATUS_ID, op: '=', value: 'Wanted' };
		expect(describeCondition(wanted, lookup)).toBe('Saved field › Status: is Wanted');
		const recent: Condition = {
			kind: 'field',
			origin: ACQ_ID,
			sub_key: 'date',
			op: '>=',
			value: { rel: '-30d' }
		};
		expect(describeCondition(recent, lookup)).toBe(
			'Saved field › Acquisition › Date: in the last 30 days'
		);
		const gone: Condition = { kind: 'field', origin: 'x', op: 'empty' };
		expect(describeCondition(gone, lookup)).toBe('Saved field › Saved field: is empty');
	});

	it('flags a saved field that is no longer listed, unless the listing is unread', () => {
		const gone: Condition = { kind: 'field', origin: 'x', op: 'empty' };
		expect(fieldStatus(gone, catalogue)).toBe('missing');
		expect(missingFieldMessage(gone)).toBe(GONE_SAVED_FIELD_MESSAGE);
		expect(fieldStatus(gone, buildCatalogue(types, true, own, null))).toBe('ok');
		const ok: Condition = { kind: 'field', origin: STATUS_ID, op: 'empty' };
		expect(fieldStatus(ok, catalogue)).toBe('ok');
	});
});
