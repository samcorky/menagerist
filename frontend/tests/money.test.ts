import { describe, it, expect } from 'vitest';
import { moneyCurrencyName, moneyText } from '../src/lib/field-types/money/format';
import { CURRENCIES, currencyByCode } from '../src/lib/field-types/money/currencies';
import { getDescriptor, fieldFromProperty, propertyFromField } from '../src/lib/field-types';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

describe('moneyText', () => {
	it('shows a two-decimal, symbol-prefixed amount for a known-symbol currency', () => {
		expect(moneyText({ value: 45, currency: 'GBP' })).toBe('£45.00');
		expect(moneyText({ value: 120.5, currency: 'USD' })).toBe('$120.50');
	});

	it('falls back to "{value} {code}" for a currency with no known symbol', () => {
		expect(moneyText({ value: 45, currency: 'BAM' })).toBe('45.00 BAM');
	});

	it('shows just the amount or just the currency when the other half is missing', () => {
		expect(moneyText({ value: 45 })).toBe('45.00');
		expect(moneyText({ currency: 'GBP' })).toBe('GBP');
	});

	it('returns an empty string for no value, non-object, or an empty object', () => {
		expect(moneyText({})).toBe('');
		expect(moneyText(undefined)).toBe('');
		expect(moneyText('45 GBP')).toBe('');
	});

	it('accepts a numeric string value, as read-mode rendering passes through attributesToRows', () => {
		expect(moneyText({ value: '45', currency: 'GBP' })).toBe('£45.00');
		expect(moneyText({ value: 'not-a-number', currency: 'GBP' })).toBe('GBP');
	});

	it('looks up the full currency name for the money view tooltip', () => {
		expect(moneyCurrencyName({ value: 45, currency: 'GPL' })).toBe('Gold-Pressed Latinum');
		expect(moneyCurrencyName({ value: 45, currency: 'GBP' })).toBe('British Pound');
		expect(moneyCurrencyName({ value: 45, currency: 'ZZZ' })).toBeUndefined();
		expect(moneyCurrencyName({ value: 45 })).toBeUndefined();
	});
});

describe('currencies', () => {
	it('includes the full curated list with codes, names and symbols where known', () => {
		expect(CURRENCIES.length).toBeGreaterThan(100);
		expect(currencyByCode('GBP')).toEqual({ code: 'GBP', name: 'British Pound', symbol: '£' });
		expect(currencyByCode('USD')?.symbol).toBe('$');
		expect(currencyByCode('EUR')?.symbol).toBe('€');
		expect(currencyByCode('JPY')?.symbol).toBe('¥');
	});

	it('omits a symbol for currencies with no common one', () => {
		const noSymbol = currencyByCode('BAM');
		expect(noSymbol).toBeDefined();
		expect(noSymbol?.symbol).toBeUndefined();
	});

	it('returns undefined for an unknown code', () => {
		expect(currencyByCode('ZZZ')).toBeUndefined();
	});

	it('includes fictional currencies as selectable options', () => {
		expect(currencyByCode('GPL')).toEqual({ code: 'GPL', name: 'Gold-Pressed Latinum' });
		expect(currencyByCode('ZRU')).toEqual({ code: 'ZRU', name: 'Hyrule Rupee' });
		expect(moneyText({ value: 25, currency: 'GPL' })).toBe('25.00 GPL');
	});
});

describe('money descriptor', () => {
	const moneyProp = {
		title: 'Purchase price',
		type: 'object',
		properties: {
			value: { title: 'Value', type: 'number' },
			currency: { title: 'Currency', type: 'string' }
		},
		'x-menagerist': { kind: 'money' }
	} as JsonSchemaProperty;

	it('is registered and matched only by its explicit kind', () => {
		expect(getDescriptor('money')).toBeDefined();
		expect(fieldFromProperty('purchase_price', moneyProp, false).kind).toBe('money');

		const plainObject = {
			title: 'Purchase price',
			type: 'object',
			properties: moneyProp.type === 'object' ? moneyProp.properties : {}
		} as JsonSchemaProperty;
		expect(fieldFromProperty('purchase_price', plainObject, false).kind).toBe('opaque');
	});

	it('round-trips through the editor field', () => {
		expect(propertyFromField(fieldFromProperty('purchase_price', moneyProp, false))).toEqual(
			moneyProp
		);
	});

	it('is offered as a group sub-field', () => {
		expect(getDescriptor('money')?.canBeSubField).toBe(true);
	});

	it('formatSummary renders the same formatted string as the view, or null when empty', () => {
		const desc = getDescriptor('money')!;
		expect(desc.formatSummary?.({ value: 45, currency: 'GBP' }, moneyProp)).toBe('£45.00');
		expect(desc.formatSummary?.({}, moneyProp)).toBeNull();
	});

	it('writes the constrained object shape for a new field', () => {
		const field = {
			key: 'purchase_price',
			label: 'Purchase price',
			kind: 'money',
			required: false,
			options: [],
			subFields: []
		};
		expect(propertyFromField(field)).toEqual(moneyProp);
	});
});
