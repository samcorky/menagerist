import { describe, expect, it } from 'vitest';
import {
	applyDraft,
	blankCondition,
	chipModels,
	conditionFor,
	conditionNumbers,
	conditionProblem,
	draftPathFor,
	fieldSubject,
	fromWidget,
	queryKey,
	relative,
	relativeParts,
	sortFromValue,
	sortValue,
	toWidget,
	valueShape,
	withOperator,
	withSubject
} from '$lib/query/builder';
import {
	canCompareWithField,
	filterableFields,
	findField,
	refCandidates,
	sortableFields,
	summaryLookup
} from '$lib/query/fields';
import { canAddCondition } from '$lib/query/limits';
import { addCondition, emptyQuery, removeAt, replaceAt } from '$lib/query/tree';
import type { Condition, Query } from '$lib/query/types';
import { catalogue } from './query-builder-fixtures';

const field = (key: string, subKey?: string) => {
	const found = findField(catalogue, 'film', key, subKey);
	if (!found) throw new Error(`no field ${key}`);
	return found;
};

describe('field catalogue', () => {
	it('offers non-archived fields whose kind has operators, with table columns', () => {
		const labels = filterableFields(catalogue).map((f) => `${f.typeLabel} › ${f.label}`);
		expect(labels).toContain('Film › Rating');
		expect(labels).toContain('Film › Cast › Role');
		expect(labels).not.toContain('Film › Old');
		expect(labels).not.toContain('Film › Cast');
	});

	it('offers same-kind fields of the same type for comparison', () => {
		expect(refCandidates(catalogue, field('stock')).map((f) => f.key)).toEqual(['reorder_at']);
		expect(canCompareWithField(catalogue, field('note'))).toBe(false);
		expect(canCompareWithField(catalogue, field('rating'))).toBe(false);
		expect(canCompareWithField(catalogue, field('cast', 'role'))).toBe(false);
	});

	it('sorts only on sortable top-level fields', () => {
		const keys = sortableFields(catalogue).map((f) => f.key);
		expect(keys).toContain('rating');
		expect(keys).not.toContain('seen');
		expect(keys).not.toContain('cast');
	});

	it('formats values as the cards do', () => {
		const lookup = summaryLookup(catalogue);
		expect(lookup.formatValue?.('film', 'price', undefined, { value: 3.5, currency: 'GBP' })).toBe(
			'£3.50'
		);
		expect(lookup.formatValue?.('film', 'runtime', undefined, 2700)).toBe('45:00');
		expect(lookup.formatValue?.('film', 'year', undefined, '1984')).toBe('1984');
		expect(lookup.formatValue?.('film', 'rating', undefined, 4)).toBe('4 stars');
		expect(lookup.formatValue?.('film', 'gone', undefined, 4)).toBeNull();
	});
});

describe('editing rows', () => {
	it('adding a condition and choosing a field yields the expected tree', () => {
		let query = addCondition(emptyQuery(), [], blankCondition());
		const chosen = withSubject(blankCondition(), fieldSubject('film', 'rating'), catalogue);
		query = replaceAt(query, [0], chosen);
		query = replaceAt(query, [0], withOperator(chosen, '>=', catalogue));
		query = replaceAt(query, [0], {
			...(query.where?.children[0] as Condition),
			value: fromWidget('rating', '4')
		} as Condition);
		expect(applyDraft(query, catalogue).query).toEqual({
			v: 1,
			where: {
				op: 'and',
				children: [{ kind: 'field', type: 'film', key: 'rating', op: '>=', value: 4 }]
			},
			sort: []
		});
	});

	it('switching to a field of another kind resets the operator and value', () => {
		const before: Condition = { kind: 'field', type: 'film', key: 'rating', op: '>', value: 4 };
		expect(withSubject(before, fieldSubject('film', 'format'), catalogue)).toEqual({
			kind: 'field',
			type: 'film',
			key: 'format',
			op: '='
		});
	});

	it('keeps the value when the operator keeps its shape, and resets it otherwise', () => {
		const c: Condition = { kind: 'field', type: 'film', key: 'stock', op: '>', value: 3 };
		expect(withOperator(c, '<=', catalogue)).toEqual({ ...c, op: '<=' });
		expect(withOperator(c, 'between', catalogue)).toEqual({ ...c, op: 'between', value: ['', ''] });
		expect(withOperator(c, 'empty', catalogue)).toEqual({
			kind: 'field',
			type: 'film',
			key: 'stock',
			op: 'empty'
		});
	});

	it('keeps the chosen values when switching between in and not_in', () => {
		const choice: Condition = {
			kind: 'field',
			type: 'film',
			key: 'format',
			op: 'in',
			value: ['DVD', 'Blu-ray']
		};
		const flipped = withOperator(choice, 'not_in', catalogue);
		expect(flipped).toEqual({ ...choice, op: 'not_in' });
		expect(withOperator(flipped, 'in', catalogue)).toEqual(choice);
		const text: Condition = { kind: 'field', type: 'film', key: 'note', op: 'in', value: ['a'] };
		expect(withOperator(text, 'not_in', catalogue)).toEqual({ ...text, op: 'not_in' });
	});

	it('starts general subjects with sensible defaults', () => {
		expect(conditionFor('created', catalogue)).toEqual({
			kind: 'date',
			on: 'created',
			op: '>=',
			value: { rel: '-30d' }
		});
		expect(conditionFor('favourite', catalogue)).toEqual({ kind: 'favourite', value: true });
		expect(conditionFor(fieldSubject('film', 'role', 'role'), catalogue)).toEqual(blankCondition());
		expect(conditionFor(fieldSubject('film', 'cast', 'role'), catalogue)).toEqual({
			kind: 'field',
			type: 'film',
			key: 'cast',
			sub_key: 'role',
			op: '='
		});
	});

	it('picks a value input per operator', () => {
		expect(valueShape('number', 'between')).toBe('range');
		expect(valueShape('choice', 'in')).toBe('multi');
		expect(valueShape('text', 'in')).toBe('list');
		expect(valueShape('choice', 'not_in')).toBe('multi');
		expect(valueShape('text', 'not_in')).toBe('list');
		expect(valueShape('url', 'not_in')).toBe('list');
		expect(valueShape('multichoice', 'has')).toBe('multi');
		expect(valueShape('boolean', '=')).toBe('boolean');
		expect(valueShape('number', 'empty')).toBe('none');
		expect(valueShape('text', '~')).toBe('single');
	});

	it('converts widget values and back, keeping invalid input editable', () => {
		expect(fromWidget('number', '12.5')).toBe(12.5);
		expect(fromWidget('number', 'abc')).toBe('abc');
		expect(fromWidget('number', '')).toBeUndefined();
		expect(fromWidget('money', { value: '3.50', currency: 'GBP' })).toEqual({
			value: 3.5,
			currency: 'GBP'
		});
		expect(fromWidget('boolean', 'false')).toBe(false);
		expect(toWidget('money', 'nonsense')).toEqual({});
		expect(toWidget('number', { rel: '-1d' })).toBe('');
		expect(toWidget('number', 4)).toBe('4');
	});

	it.each(
		['-', '+'].flatMap((sign) =>
			['d', 'w', 'm', 'y'].flatMap((unit) => ['0', '1', '999'].map((n) => `${sign}${n}${unit}`))
		)
	)('keeps %s through an edit round trip', (rel) => {
		const { count, mode } = relativeParts({ rel });
		expect(relative(count, mode)).toEqual({ rel });
	});

	it('builds relative dates', () => {
		expect(relative('2', '-w')).toEqual({ rel: '-2w' });
		expect(relative('5', '+d')).toEqual({ rel: '+5d' });
		expect(relativeParts({ rel: '-30d' })).toEqual({ count: '30', mode: '-d' });
		expect(relativeParts({ rel: '+5d' })).toEqual({ count: '5', mode: '+d' });
		expect(relativeParts({ rel: '5d' })).toEqual({ count: '5', mode: '+d' });
		expect(relativeParts('2024-01-01')).toEqual({ count: '', mode: '-d' });
	});
});

describe('conditionProblem', () => {
	it.each<[Condition, string | null]>([
		[{ kind: 'field', type: 'film', key: 'stock', op: '>', value: 'abc' }, 'Enter a number.'],
		[
			{ kind: 'field', type: 'film', key: 'stock', op: '>', value: { rel: '-1d' } },
			'Enter a value.'
		],
		[{ kind: 'field', type: 'film', key: 'stock', op: '>', value: { ref: 'reorder_at' } }, null],
		[
			{ kind: 'field', type: 'film', key: 'stock', op: 'between', value: [1, 'x'] },
			'Enter a number.'
		],
		[
			{ kind: 'field', type: 'film', key: 'stock', op: 'between', value: 3 },
			'Enter both ends of the range.'
		],
		[{ kind: 'field', type: 'film', key: 'stock', op: '~', value: 3 }, 'Choose how to compare.'],
		[
			{ kind: 'field', type: 'film', key: 'price', op: '>', value: 3 },
			'Enter an amount and a currency.'
		],
		[{ kind: 'field', type: 'film', key: 'released', op: '>', value: 5 }, 'Choose a date.'],
		[{ kind: 'field', type: 'film', key: 'released', op: '>', value: { rel: '-2w' } }, null],
		[
			{ kind: 'field', type: 'film', key: 'format', op: 'in', value: [] },
			'Choose at least one value.'
		],
		[
			{ kind: 'field', type: 'film', key: 'format', op: 'not_in', value: [] },
			'Choose at least one value.'
		],
		[{ kind: 'field', type: 'film', key: 'format', op: 'not_in', value: ['DVD'] }, null],
		[{ kind: 'field', type: 'film', key: 'gone', op: '>', value: 'x' }, null],
		[
			{ kind: 'date', on: 'created', op: '>=', value: { rel: '-xd' } },
			expect.any(String) as unknown as string
		],
		[{ kind: 'tag', mode: 'any', tags: [] }, 'Add at least one tag.'],
		[{ kind: 'text', q: '  ' }, 'Enter some words to look for.'],
		[blankCondition(), 'Choose what to filter on.']
	])('%j', (condition, expected) => {
		expect(conditionProblem(condition, catalogue)).toEqual(expected);
	});
});

describe('applyDraft', () => {
	it('drops unfinished rows and empty groups, mapping the kept paths', () => {
		const draft: Query = {
			v: 1,
			where: {
				op: 'and',
				children: [
					blankCondition(),
					{ kind: 'favourite', value: true },
					{ op: 'or', children: [blankCondition()] },
					{
						op: 'or',
						children: [
							blankCondition(),
							{ kind: 'field', type: 'film', key: 'seen', op: '=', value: true }
						]
					}
				]
			},
			sort: []
		};
		const { query, toApplied } = applyDraft(draft, catalogue);
		expect(query.where).toEqual({
			op: 'and',
			children: [
				{ kind: 'favourite', value: true },
				{ op: 'or', children: [{ kind: 'field', type: 'film', key: 'seen', op: '=', value: true }] }
			]
		});
		expect(toApplied.get('3.1')).toBe('1.0');
		expect(draftPathFor(toApplied, '1.0')).toEqual([3, 1]);
	});

	it('removing the last condition clears the filter', () => {
		const one: Query = {
			v: 1,
			where: { op: 'and', children: [{ kind: 'favourite', value: true }] },
			sort: []
		};
		const after = applyDraft(removeAt(one, [0]), catalogue).query;
		expect(after.where).toBeNull();
	});

	it('numbers conditions in reading order', () => {
		const draft: Query = {
			v: 1,
			where: {
				op: 'and',
				children: [blankCondition(), { op: 'or', children: [blankCondition(), blankCondition()] }]
			},
			sort: []
		};
		expect([...conditionNumbers(draft)]).toEqual([
			['0', 1],
			['1.0', 2],
			['1.1', 3]
		]);
	});
});

describe('limits in the builder', () => {
	it('stops adding conditions at 50', () => {
		const full: Query = {
			v: 1,
			where: {
				op: 'and',
				children: Array.from({ length: 50 }, () => ({ kind: 'favourite', value: true }) as const)
			},
			sort: []
		};
		expect(canAddCondition(full)).toBe(false);
		expect(canAddCondition(removeAt(full, [0]))).toBe(true);
	});
});

describe('chipModels', () => {
	const lookup = summaryLookup(catalogue);
	const query: Query = {
		v: 1,
		where: {
			op: 'and',
			children: [
				{
					kind: 'field',
					type: 'film',
					key: 'price',
					op: '<=',
					value: { value: 3.5, currency: 'GBP' }
				},
				{
					op: 'or',
					children: [
						{ kind: 'field', type: 'film', key: 'runtime', op: '<=', value: 2700 },
						{ kind: 'field', type: 'film', key: 'gone', op: '=', value: 1 }
					]
				}
			]
		},
		sort: []
	};

	it('describes each top-level row with formatted values', () => {
		const { lead, chips } = chipModels(query, lookup, new Set(['1.1']));
		expect(lead).toBeNull();
		expect(chips.map((c) => c.text)).toEqual([
			'Film: Price is at most £3.50',
			'Any of: Film: Runtime is at most 45:00; Film: gone is 1'
		]);
		expect(chips.map((c) => c.warning)).toEqual([false, true]);
		expect(chips[1].focus).toEqual([1, 0]);
	});

	it('says when the top level matches any', () => {
		const any: Query = { ...query, where: { ...query.where!, op: 'or' } };
		expect(chipModels(any, lookup).lead).toBe('Any of these:');
	});
});

describe('sort', () => {
	it('round-trips the sort choice', () => {
		expect(sortValue([])).toBe('default');
		expect(sortFromValue('default', 'asc')).toEqual([]);
		expect(sortFromValue('name', 'desc')).toEqual([{ by: 'name', dir: 'desc' }]);
		const value = fieldSubject('film', 'rating');
		expect(sortFromValue(value, 'asc')).toEqual([
			{ by: 'field', type: 'film', key: 'rating', dir: 'asc' }
		]);
		expect(sortValue(sortFromValue(value, 'asc'))).toBe(value);
	});
});

describe('queryKey', () => {
	it('ignores member order', () => {
		const a: Query = {
			v: 1,
			where: { op: 'and', children: [{ kind: 'field', type: 't', key: 'k', op: '=', value: 1 }] },
			sort: []
		};
		const b = {
			sort: [],
			where: { children: [{ value: 1, op: '=', key: 'k', type: 't', kind: 'field' }], op: 'and' },
			v: 1
		} as unknown as Query;
		expect(queryKey(a)).toBe(queryKey(b));
	});
});
