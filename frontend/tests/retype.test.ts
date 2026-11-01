import { describe, expect, it } from 'vitest';
import { retypeImpact } from '$lib/retype';
import type { AttributesSchema } from '$lib/schema-types';

const schema = (...keys: string[]): AttributesSchema =>
	({
		$schema: 'https://json-schema.org/draft/2020-12/schema',
		type: 'object',
		properties: Object.fromEntries(keys.map((key) => [key, { type: 'string', title: key }]))
	}) as AttributesSchema;

describe('retypeImpact', () => {
	it('has no impact when every value has a field in the new type', () => {
		const impact = retypeImpact({ year: 1979 }, schema('year'), null);
		expect(impact).toEqual({ orphaned: [], clashes: [] });
	});

	it('lists values the new type has no field for, labelled by key', () => {
		const impact = retypeImpact({ year: 1979, runtime: 117 }, schema('year'), null);
		expect(impact.orphaned).toEqual(['runtime']);
	});

	it('counts the item’s own added fields as homes for values', () => {
		const impact = retypeImpact({ runtime: 117 }, schema('year'), schema('runtime'));
		expect(impact.orphaned).toEqual([]);
	});

	it('treats every value as orphaned when clearing the type, unless an item field holds it', () => {
		const impact = retypeImpact({ year: 1979, note: 'x' }, null, schema('note'));
		expect(impact.orphaned).toEqual(['year']);
	});

	it('reports item fields that share a name with the new type’s fields', () => {
		const impact = retypeImpact({ year: 1979 }, schema('year', 'cast'), schema('year', 'mine'));
		expect(impact.clashes).toEqual(['year']);
	});

	it('does not count empty values as orphaned', () => {
		const impact = retypeImpact({ runtime: null, notes: '' }, schema('year'), null);
		expect(impact.orphaned).toEqual([]);
	});
});
