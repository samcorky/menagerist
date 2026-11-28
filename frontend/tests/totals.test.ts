import { describe, expect, it } from 'vitest';
import { buildCatalogue } from '$lib/query/fields';
import {
	automaticTotals,
	collectionTotalsQuery,
	describeTotal,
	formatMoney,
	formatResult,
	functionsFor,
	shownTotals,
	totalChoices,
	totalField,
	totalKey
} from '$lib/totals';

const money = (preset?: string) => ({
	type: 'object',
	title: 'Price',
	'x-menagerist': { kind: 'money', ...(preset ? { origin: { preset } } : {}) }
});
const num = (title: string) => ({ type: 'number', title });

const catalogue = buildCatalogue([
	{
		slug: 'film',
		label: 'Film',
		attributes_schema: {
			type: 'object',
			properties: {
				price: money(),
				paid: money(),
				budget: money(),
				cost: money(),
				runtime: num('Runtime'),
				score: num('Score'),
				extra: num('Extra'),
				old: { type: 'number', 'x-menagerist': { archived: true } }
			}
		}
	},
	{
		slug: 'documentary',
		label: 'Documentary',
		parent: 'film',
		effective_schema: {
			type: 'object',
			properties: { price: money(), paid: money(), budget: money(), cost: money() }
		},
		attributes_schema: { type: 'object', properties: {} }
	},
	{
		slug: 'book',
		label: 'Book',
		attributes_schema: { type: 'object', properties: { cost: money('p1'), pages: num('Pages') } }
	}
]);

describe('automaticTotals', () => {
	it('adds up at most three money fields and averages at most two number fields', () => {
		const totals = automaticTotals(catalogue, ['film']);

		expect(totals).toEqual([
			{ fn: 'sum', type: 'film', key: 'price' },
			{ fn: 'sum', type: 'film', key: 'paid' },
			{ fn: 'sum', type: 'film', key: 'budget' },
			{ fn: 'avg', type: 'film', key: 'runtime' },
			{ fn: 'avg', type: 'film', key: 'score' }
		]);
	});

	it('reads a subtype through its parent and never twice', () => {
		const totals = automaticTotals(catalogue, ['documentary']);

		expect(totals.map((t) => t.type)).toEqual(['film', 'film', 'film', 'film', 'film']);
	});

	it('uses the saved field so one total covers every type', () => {
		expect(automaticTotals(catalogue, ['book'])).toEqual([
			{ fn: 'sum', origin: 'p1' },
			{ fn: 'avg', type: 'book', key: 'pages' }
		]);
	});

	it('shows nothing for an empty collection or types with nothing to total', () => {
		expect(automaticTotals(catalogue, [])).toEqual([]);
		expect(automaticTotals(catalogue, ['missing'])).toEqual([]);
	});
});

describe('shownTotals', () => {
	it('prefers the person’s choice, even an empty one', () => {
		const auto = [{ fn: 'sum' as const, type: 'film', key: 'price' }];

		expect(shownTotals(null, auto)).toBe(auto);
		expect(shownTotals(undefined, auto)).toBe(auto);
		expect(shownTotals([], auto)).toEqual([]);
	});
});

describe('totalChoices and functionsFor', () => {
	it('offers each own field that can be totalled, sorted, labelled with its type', () => {
		const labels = totalChoices(catalogue).map((c) => c.label);

		expect(labels).toContain('Price (Film)');
		expect(labels).toContain('Pages (Book)');
		expect(labels).not.toContain('Price (Documentary)');
		expect(labels).toEqual([...labels].sort((a, b) => a.localeCompare(b, 'en-GB')));
	});

	it('says which functions a kind takes', () => {
		expect(functionsFor('money')).toEqual(['sum', 'avg', 'min', 'max']);
		expect(functionsFor('date')).toEqual(['min', 'max']);
		expect(functionsFor('text')).toEqual([]);
	});
});

describe('describeTotal', () => {
	it('names the function and the field', () => {
		expect(describeTotal({ fn: 'sum', type: 'film', key: 'price' }, catalogue)).toBe('Total price');
		expect(describeTotal({ fn: 'avg', type: 'film', key: 'score' }, catalogue)).toBe(
			'Average score'
		);
		expect(describeTotal({ fn: 'count' }, catalogue)).toBe('Items');
	});

	it('falls back to the key for a field that is gone', () => {
		expect(describeTotal({ fn: 'sum', type: 'film', key: 'gone' }, catalogue)).toBe('Total gone');
	});
});

describe('formatResult', () => {
	it('gives each currency its own value, never added together', () => {
		const shown = formatResult(
			{
				value: null,
				currencies: [
					{ currency: 'GBP', value: 1204.5 },
					{ currency: 'USD', value: 80 }
				]
			},
			undefined
		);

		expect(shown).toEqual([
			{ text: '£1,204.50', currency: 'GBP' },
			{ text: 'US$80.00', currency: 'USD' }
		]);
	});

	it('reads a number, a dash for none, and an unknown currency by its code', () => {
		expect(formatResult({ value: 3.456, currencies: [] }, undefined)).toEqual([{ text: '3.46' }]);
		expect(formatResult({ value: null, currencies: [] }, undefined)).toEqual([{ text: '–' }]);
		expect(formatMoney(5, 'nope')).toBe('5 nope');
	});

	it('reads a rating as a number and a text value as it is', () => {
		const rating = totalField({ fn: 'avg', type: 'film', key: 'score' }, catalogue);

		expect(formatResult({ value: 3.5, currencies: [] }, rating)).toEqual([{ text: '3.5' }]);
		expect(formatResult({ value: '2020-01-05', currencies: [] }, undefined)).toEqual([
			{ text: '2020-01-05' }
		]);
	});
});

describe('collectionTotalsQuery and totalKey', () => {
	it('asks about every item on the collection', () => {
		expect(collectionTotalsQuery('c1')).toEqual({
			v: 1,
			where: { op: 'and', children: [{ kind: 'collection', mode: 'any', in: ['c1'] }] }
		});
	});

	it('keys the same measure the same way', () => {
		expect(totalKey({ fn: 'sum', type: 'film', key: 'price' })).toBe(
			totalKey({ key: 'price', type: 'film', fn: 'sum' })
		);
		expect(totalKey({ fn: 'sum', type: 'film', key: 'price' })).not.toBe(
			totalKey({ fn: 'avg', type: 'film', key: 'price' })
		);
	});
});
