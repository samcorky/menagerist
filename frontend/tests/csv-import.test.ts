import { describe, expect, it } from 'vitest';
import type { ItemImportFieldResponse } from '$lib/api/client';
import {
	addedText,
	BUILT_IN_TARGETS,
	assignTarget,
	choicesFrom,
	confirmText,
	connectColumn,
	connectionEntries,
	connectionsReady,
	deletedRows,
	fieldTitles,
	hasName,
	itemsToAdd,
	keepColumn,
	keptDetails,
	keyColumns,
	keyFieldFor,
	mappingEntries,
	MAX_CONNECTED,
	MAX_KEPT,
	namedToCreate,
	renameKept,
	rowEndOptions,
	setKeptKind,
	rowsAndColumns,
	targetOptions,
	type ColumnChoice,
	waitingText
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

describe('choicesFrom and mappingEntries', () => {
	it('turns the suggested mapping into choices, keeping null targets', () => {
		expect(
			choicesFrom([{ column: 'a', target: 'name' }, { column: 'b' }, { column: 'c', target: null }])
		).toEqual([
			{ column: 'a', target: 'name' },
			{ column: 'b', target: null },
			{ column: 'c', target: null }
		]);
	});

	it('sends each column with its target', () => {
		expect(mappingEntries(choices, [])).toEqual(choices);
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
		const sent = mappingEntries(next, ['signed_on']);
		expect(sent[2].extra).toEqual({ key: 'signed_on_2', title: 'Signed on', kind: 'text' });
		expect(sent[3].extra?.key).toBe('signed_on_3');
	});

	it('never gives a detail the key of a built-in target', () => {
		const next = renameKept(keepColumn(choices, 'misc', 'text'), 'misc', 'Name');
		expect(mappingEntries(next, [])[2].extra?.key).toBe('name_2');
	});

	it('lists the kept details for the preview', () => {
		let next = keepColumn(choices, 'misc', 'boolean');
		next = renameKept(next, 'misc', 'Signed');
		expect(keptDetails(next)).toEqual([{ title: 'Signed', kind: 'boolean' }]);
	});

	it('joins a detail the items of the type already have, taking its key and kind', () => {
		let next = keepColumn(choices, 'misc', 'text');
		next = renameKept(next, 'misc', 'signed', { key: 'signed', kind: 'boolean' });
		expect(next[2].extra).toEqual({ title: 'signed', kind: 'boolean', key: 'signed' });
		expect(mappingEntries(next, [])[2].extra).toEqual({
			key: 'signed',
			title: 'signed',
			kind: 'boolean'
		});
	});

	it('stops joining when the name or the kind changes', () => {
		let joined = keepColumn(choices, 'misc', 'text');
		joined = renameKept(joined, 'misc', 'Signed', { key: 'signed', kind: 'boolean' });
		expect(renameKept(joined, 'misc', 'Signed by')[2].extra?.key).toBeUndefined();
		expect(setKeptKind(joined, 'misc', 'text')[2].extra?.key).toBeUndefined();
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
		reason: null,
		changed: [],
		deleted: false
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

describe('recognising rows by a key column', () => {
	const keyed: ColumnChoice[] = [
		{ column: 'ID', target: null, extra: { title: 'Ref', kind: 'text' } },
		{ column: 'Who', target: 'name' },
		{ column: 'When', target: 'signed_on' },
		{ column: 'Notes', target: 'description' },
		{ column: 'Labels', target: 'tags' },
		{ column: 'Misc', target: null }
	];

	it('offers the name, mapped fields and kept details, in column order', () => {
		expect(keyColumns(keyed)).toEqual(['ID', 'Who', 'When']);
	});

	it('sends the field a column fills, or the key a kept detail is given', () => {
		const sent = mappingEntries(keyed, ['signed_on']);
		expect(keyFieldFor(keyed, ['signed_on'], 'ID')).toBe(sent[0].extra?.key);
		expect(keyFieldFor(keyed, ['signed_on'], 'Who')).toBe('name');
		expect(keyFieldFor(keyed, ['signed_on'], 'When')).toBe('signed_on');
		expect(keyFieldFor(keyed, ['signed_on'], null)).toBeNull();
	});

	it('names each changed field as people see it', () => {
		const titles = fieldTitles(keyed, [field('signed_on', { title: 'Signed on' })]);
		expect(titles['name']).toBe('Name');
		expect(titles['attributes.signed_on']).toBe('Signed on');
		expect(titles[`attributes.${keyFieldFor(keyed, ['signed_on'], 'ID')}`]).toBe('Ref');
	});
});

describe('deletedRows', () => {
	const row = (
		label: string,
		action: 'create' | 'unchanged' | 'skip',
		over: Partial<ImportPlan['entities'][number]> = {}
	) => ({
		kind: 'item',
		ref: label,
		label,
		action,
		reason: null,
		changed: [],
		deleted: false,
		...over
	});

	it('lists rows and connections deleted after importing, and keeps a restored one ticked', () => {
		const plan: ImportPlan = {
			ready: true,
			blockers: [],
			entities: [
				row('Gone', 'skip', { source_key: '5', deleted: true }),
				row('Back', 'create', { source_key: '6' }),
				row('No key', 'skip', { reason: 'No key.' }),
				row('Kept', 'unchanged', { source_key: '7', matched_id: 'x', matched_name: 'Kept' }),
				row('New', 'create', { source_key: '8' }),
				row('Photo to eBay', 'skip', { kind: 'connection', source_key: 'c1', deleted: true })
			]
		};

		expect(deletedRows(plan, ['6'])).toEqual([
			{ key: '5', label: 'Gone', restored: false },
			{ key: '6', label: 'Back', restored: true },
			{ key: 'c1', label: 'Photo to eBay', restored: false }
		]);
	});
});

describe('connecting a column to items by name', () => {
	const base: ColumnChoice[] = [
		{ column: 'title', target: 'name' },
		{ column: 'where', target: null }
	];
	const ready = connectColumn(base, 'where', {
		relationship_type: 'obtained-at',
		item_type: 'event'
	});

	it('sends one entry for a connected column, creating missing items by default', () => {
		expect(connectionEntries(ready)).toEqual([
			{
				column: 'where',
				relationship_type: 'obtained-at',
				item_type: 'event',
				row_end: 'source',
				on_missing: 'create'
			}
		]);
		expect(mappingEntries(ready, [])).toEqual([
			{ column: 'title', target: 'name' },
			{ column: 'where', target: null }
		]);
	});

	it('keeps the settings chosen so far when one more changes', () => {
		const next = connectColumn(ready, 'where', { on_missing: 'skip' });

		expect(connectionEntries(next)[0]).toMatchObject({
			item_type: 'event',
			on_missing: 'skip'
		});
	});

	it('waits for a connection type and an item type before it is ready', () => {
		const started = connectColumn(base, 'where');

		expect(connectionsReady(started)).toBe(false);
		expect(connectionEntries(started)).toEqual([]);
		expect(connectionsReady(ready)).toBe(true);
	});

	it('stops connecting when the column is matched to a field instead', () => {
		expect(connectionEntries(assignTarget(ready, 'where', 'description'))).toEqual([]);
	});

	it('refuses a sixth connected column', () => {
		const many: ColumnChoice[] = Array.from({ length: MAX_CONNECTED + 1 }, (_, i) => ({
			column: `c${i}`,
			target: null
		}));
		const five = many
			.slice(0, MAX_CONNECTED)
			.reduce((acc, c) => connectColumn(acc, c.column), many);

		const six = connectColumn(five, `c${MAX_CONNECTED}`);

		expect(six).toBe(five);
	});

	it('words which end the row is from the connection type', () => {
		expect(rowEndOptions({ label: 'Signed by', directional: true })).toEqual([
			{ value: 'source', label: "This row's item signed by the other item" },
			{ value: 'target', label: "The other item signed by this row's item" }
		]);
	});

	it('names the items the connected columns would create', () => {
		const plan: ImportPlan = {
			ready: true,
			blockers: [],
			entities: [
				{
					kind: 'item',
					ref: 'row-2',
					label: 'Photo',
					action: 'create',
					changed: [],
					deleted: false
				},
				{
					kind: 'item',
					ref: 'named-0',
					label: 'eBay',
					action: 'create',
					changed: [],
					deleted: false
				},
				{
					kind: 'item',
					ref: 'named-1',
					label: 'Comic Con',
					action: 'unchanged',
					changed: [],
					deleted: false
				}
			]
		};

		expect(namedToCreate(plan)).toEqual(['eBay']);
	});
});

describe('addedText and waitingText', () => {
	it('says what an import added, naming connections only when there are some', () => {
		expect(addedText({ items_added: 1, connections_added: 0 })).toBe('Added 1 item');
		expect(addedText({ items_added: 1200, connections_added: 1 })).toBe(
			'Added 1,200 items and 1 connection'
		);
		expect(addedText({ items_added: 2, connections_added: 3 })).toBe(
			'Added 2 items and 3 connections'
		);
	});

	it('says how many imports run first', () => {
		expect(waitingText(0)).toBe('Starting soon…');
		expect(waitingText(null)).toBe('Starting soon…');
		expect(waitingText(1)).toBe('Waiting for 1 other import to finish first');
		expect(waitingText(3)).toBe('Waiting for 3 other imports to finish first');
	});
});
