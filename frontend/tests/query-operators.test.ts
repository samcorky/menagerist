import { describe, expect, it } from 'vitest';
import contract from '$shared/contracts/query-operators.json';
import kinds from '$shared/contracts/query-kinds.json';
import { REF_KINDS, SORTABLE_KINDS } from '$lib/query/fields';
import {
	KIND_OPERATORS,
	OPERATOR_LABELS,
	operatorsForKind,
	operatorTakesValue
} from '$lib/query/operators';

const normalise = (table: Record<string, readonly string[]>) =>
	Object.fromEntries(Object.entries(table).map(([k, v]) => [k, [...v].sort()]));

describe('operator table', () => {
	it('matches the shared contract exactly', () => {
		expect(normalise(KIND_OPERATORS)).toEqual(normalise(contract));
	});

	it('labels every operator the contract uses', () => {
		const used = new Set(Object.values(contract).flat());
		for (const op of used) expect(OPERATOR_LABELS[op], op).toBeTruthy();
	});

	it('uses plain British English labels', () => {
		expect(OPERATOR_LABELS['>=']).toBe('is at least');
	});

	it('knows which operators take no value', () => {
		for (const op of ['empty', 'not_empty', 'incomplete', 'complete'])
			expect(operatorTakesValue(op)).toBe(false);
		for (const op of ['=', '~', 'between', 'in', 'has']) expect(operatorTakesValue(op)).toBe(true);
	});

	it('matches the shared reference, sortable and no-value sets', () => {
		expect([...REF_KINDS].sort()).toEqual([...kinds.ref_kinds].sort());
		expect([...SORTABLE_KINDS].sort()).toEqual([...kinds.sortable_kinds].sort());
		const used = new Set(Object.values(contract).flat());
		const noValue = [...used].filter((op) => !operatorTakesValue(op)).sort();
		expect(noValue).toEqual([...kinds.no_value_operators].sort());
	});

	it('lists operators per kind, and none for an unknown kind', () => {
		expect(operatorsForKind('boolean')).toEqual(['=', '!=']);
		expect(operatorsForKind('nope')).toEqual([]);
	});
});
