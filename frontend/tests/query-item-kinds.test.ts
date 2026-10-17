// Every kind a per-item condition can use must get a value input for every operator that takes one.
import { describe, expect, it, vi } from 'vitest';
import { render } from 'svelte/server';

vi.mock('@lucide/svelte', async () => {
	const Noop = (await import('./mocks/noop.svelte')).default;
	return {
		X: Noop,
		TriangleAlert: Noop,
		Plus: Noop,
		FolderPlus: Noop,
		ChevronDown: Noop,
		Star: Noop
	};
});
vi.mock('@lucide/svelte/icons/chevron-down', async () => ({
	default: (await import('./mocks/noop.svelte')).default
}));

import QueryValueInput from '$lib/components/query-value-input.svelte';
import { KIND_OPERATORS, LIST_OPERATORS, operatorTakesValue } from '$lib/query/operators';
import { buildCatalogue } from '$lib/query/fields';
import type { Condition } from '$lib/query/types';
import { itemTypes, stubView } from './query-builder-fixtures';

const SAMPLE: Record<string, unknown> = {
	text: 'a',
	url: 'https://a.example',
	email: 'a@example.com',
	phone: '+441234567890',
	longtext: 'a',
	number: 2,
	duration: 90,
	rating: 3,
	money: 5,
	date: '2026-01-02',
	partialdate: '2026-01',
	boolean: true,
	choice: 'a',
	multichoice: ['a'],
	checklist: undefined
};

function render1(kind: string, op: string): string {
	const value = LIST_OPERATORS.has(op)
		? [SAMPLE[kind]]
		: op === 'between'
			? [SAMPLE[kind], SAMPLE[kind]]
			: SAMPLE[kind];
	const condition = {
		kind: 'field',
		field_kind: kind,
		key: 'k',
		op,
		...(operatorTakesValue(op) ? { value } : {})
	} as Condition;
	const catalogue = buildCatalogue(itemTypes, true, [{ key: 'k', kind, label: 'K', count: 1 }]);
	return render(QueryValueInput, {
		props: { condition, name: 'Condition 1', view: stubView({ catalogue }), onchange: () => {} }
	}).body;
}

describe('per-item value input for every kind', () => {
	const cases = Object.entries(KIND_OPERATORS).flatMap(([kind, ops]) =>
		ops.map((op) => [kind, op] as const)
	);

	it.each(cases)('%s %s', (kind, op) => {
		const html = render1(kind, op);
		if (!operatorTakesValue(op)) {
			expect(html).not.toContain('Condition 1, value');
		} else if (op === 'between') {
			expect(html).toContain('Condition 1, value from');
			expect(html).toContain('Condition 1, value to');
		} else if (kind === 'boolean') {
			expect(html).toContain('aria-label="Condition 1, value"');
		} else {
			expect(html).toContain('Condition 1, value');
		}
	});
});
