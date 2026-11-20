import { describe, expect, it } from 'vitest';
import type { ItemImportFieldResponse } from '$lib/api/client';
import {
	BUILT_IN_TARGETS,
	assignTarget,
	choicesFrom,
	confirmText,
	hasName,
	itemsToAdd,
	keepColumn,
	keptDetails,
	mappingJson,
	MAX_KEPT,
	renameKept,
	setKeptKind,
	rowsAndColumns,
	targetOptions,
	type ColumnChoice
} from '$lib/csv-import';
import type { ImportPlan } from '$lib/import-plan';

function field(key: string, over: Partial<ItemImportFieldResponse> = {}): ItemImportFieldResponse {
	return { key, title: key.toUpperCase(), multiple: false, importable: true, ...over };
}

const choices: ColumnChoice[] = [
	{ column: 'title', target: 'name' },
	{ column: 'when', target: 'signed_on' },
	{ column: 'misc', target: null }
];

describe('assignTarget', () => {
	it('moves a field from the column that had it to the one that now has it', () => {
		const next = assignTarget(choices, 'misc', 'signed_on');
		expect(next).toEqual([
			{ column: 'title', target: 'name' },
			{ column: 'when', target: null },
			{ column: 'misc', target: 'signed_on' }
		]);
	});

	it('leaves unrelated columns alone when a free field is chosen', () => {
		const next = assignTarget(choices, 'misc', 'position');
		expect(next[0]).toEqual(choices[0]);
		expect(next[1]).toEqual(choices[1]);
		expect(next[2]).toEqual({ column: 'misc', target: 'position' });
	});

	it('clears only that column when given no target', () => {
		const next = assignTarget(choices, 'when', null);
		expect(next).toEqual([
			{ column: 'title', target: 'name' },
			{ column: 'when', target: null },
			{ column: 'misc', target: null }
		]);
	});

	it('does not change the list it was given', () => {
		assignTarget(choices, 'misc', 'name');
		expect(choices[0].target).toBe('name');
	});

	it('never clears several columns that have no target', () => {
		const next = assignTarget(choices, 'title', null);
		expect(next[2]).toEqual({ column: 'misc', target: null });
	});
});

describe('hasName', () => {
	it('is true when a column is matched to Name', () => {
		expect(hasName(choices)).toBe(true);
	});

	it('is false when none is', () => {
		expect(hasName(assignTarget(choices, 'title', null))).toBe(false);
		expect(hasName([])).toBe(false);
	});
});

describe('targetOptions', () => {
	it('lists the built-in targets first, then each field by title', () => {
		const options = targetOptions([field('signed_on', { title: 'Signed on' })]);
		expect(options.map((o) => o.value)).toEqual([
			...BUILT_IN_TARGETS.map((t) => t.value),
			'signed_on'
		]);
		expect(options.map((o) => o.label).slice(0, 3)).toEqual(['Name', 'Description', 'Tags']);
		expect(options.at(-1)?.label).toBe('Signed on');
	});

	it('disables a field that cannot be imported and says why', () => {
		const options = targetOptions([
			field('value', { importable: false, reason: 'Value cannot be imported yet.' })
		]);
		const money = options.at(-1);
		expect(money?.disabled).toBe(true);
		expect(money?.hint).toBe('Value cannot be imported yet.');
	});

	it('leaves importable fields enabled', () => {
		const options = targetOptions([field('position')]);
		expect(options.every((o) => !o.disabled)).toBe(true);
	});
});

describe('choicesFrom and mappingJson', () => {
	it('turns the suggested mapping into choices, keeping null targets', () => {
		expect(
			choicesFrom([{ column: 'a', target: 'name' }, { column: 'b' }, { column: 'c', target: null }])
		).toEqual([
			{ column: 'a', target: 'name' },
			{ column: 'b', target: null },
			{ column: 'c', target: null }
		]);
	});

	it('writes the JSON text the server takes, and it reads back the same', () => {
		const text = mappingJson(choices, []);
		expect(JSON.parse(text)).toEqual(choices);
	});
});

describe('keeping a column as an extra detail', () => {
	it('names the detail after the column and takes the suggested kind', () => {
		const next = keepColumn(choices, 'misc', 'number');
		expect(next[2]).toEqual({
			column: 'misc',
			target: null,
			extra: { title: 'misc', kind: 'number' }
		});
	});

	it('drops the field a column had when it is kept instead', () => {
		const next = keepColumn(choices, 'when', 'text');
		expect(next[1].target).toBeNull();
		expect(hasName(next)).toBe(true);
	});

	it('stops keeping a column once it is matched to a field again', () => {
		const kept = keepColumn(choices, 'misc', 'text');
		expect(assignTarget(kept, 'misc', 'position')[2]).toEqual({
			column: 'misc',
			target: 'position'
		});
	});

	it('renames a kept detail and changes its kind', () => {
		let next = keepColumn(choices, 'misc', 'text');
		next = renameKept(next, 'misc', 'Paper type');
		next = setKeptKind(next, 'misc', 'choice');
		expect(next[2].extra).toEqual({ title: 'Paper type', kind: 'choice' });
	});

	it('sends each kept detail with a key unique among the fields and the others', () => {
		let next = keepColumn(choices, 'misc', 'text');
		next = renameKept(next, 'misc', 'Signed on');
		next = [
			...next,
			{ column: 'other', target: null, extra: { title: 'Signed on', kind: 'text' } }
		];
		const sent = JSON.parse(mappingJson(next, ['signed_on']));
		expect(sent[2].extra).toEqual({ key: 'signed_on_2', title: 'Signed on', kind: 'text' });
		expect(sent[3].extra.key).toBe('signed_on_3');
	});

	it('never gives a detail the key of a built-in target', () => {
		const next = renameKept(keepColumn(choices, 'misc', 'text'), 'misc', 'Name');
		expect(JSON.parse(mappingJson(next, []))[2].extra.key).toBe('name_2');
	});

	it('lists the kept details for the preview', () => {
		let next = keepColumn(choices, 'misc', 'boolean');
		next = renameKept(next, 'misc', 'Signed');
		expect(keptDetails(next)).toEqual([{ title: 'Signed', kind: 'boolean' }]);
	});

	it('allows as many as an item can have', () => {
		expect(MAX_KEPT).toBe(50);
	});
});

describe('itemsToAdd', () => {
	function plan(entities: ImportPlan['entities']): ImportPlan {
		return { ready: true, blockers: [], entities };
	}
	const e = (kind: string, action: 'create' | 'unchanged' | 'conflict') => ({
		kind,
		ref: Math.random().toString(),
		label: 'x',
		action,
		reason: null
	});

	it('counts the items that would be created', () => {
		expect(itemsToAdd(plan([e('item', 'create'), e('item', 'create')]))).toBe(2);
	});

	it('ignores items already there and things that are not items', () => {
		expect(
			itemsToAdd(plan([e('item', 'unchanged'), e('item_type', 'create'), e('item', 'create')]))
		).toBe(1);
	});
});

describe('confirmText', () => {
	it('uses the singular for one', () => {
		expect(confirmText(1)).toBe('Add 1 item');
	});

	it('uses the plural and a thousands separator for many', () => {
		expect(confirmText(1204)).toBe('Add 1,204 items');
	});
});

describe('rowsAndColumns', () => {
	const inspection = (row_count: number, headers: string[]) => ({
		headers,
		sample_rows: [],
		row_count,
		fields: [],
		suggested_mapping: []
	});

	it('counts rows and columns', () => {
		expect(rowsAndColumns(inspection(1204, ['a', 'b', 'c', 'd', 'e', 'f']))).toBe(
			'1,204 rows, 6 columns'
		);
	});

	it('uses the singular for one of each', () => {
		expect(rowsAndColumns(inspection(1, ['a']))).toBe('1 row, 1 column');
	});
});
