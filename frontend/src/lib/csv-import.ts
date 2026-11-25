import type {
	ColumnMappingEntry,
	ConnectionColumnEntry,
	ConnectionEnd,
	CsvEncoding,
	DayMonthOrder,
	ExtraFieldKind,
	ItemImportFieldResponse,
	ItemImportInspectionResponse,
	NameLookup
} from '$lib/api/client';
import { generateFieldKey } from '$lib/field-key';
import type { ImportPlan } from '$lib/import-plan';

/** Where a column goes: `name`, `description`, `tags`, a field's key, or nowhere. */
export type Target = string | null;

/** A column kept as each item's own field: its name and kind. The key is made when sending. */
export interface KeptDetail {
	title: string;
	kind: ExtraFieldKind;
	/** The key of a detail the type's items already have, which this one joins. */
	key?: string;
}

/** How a column connects each row's item to another item it names. */
export interface ConnectSettings {
	/** The connection type's slug; null until chosen. */
	relationship_type: string | null;
	/** The other item's type; null until chosen. */
	item_type: string | null;
	row_end: ConnectionEnd;
	on_missing: NameLookup;
}

export interface ColumnChoice {
	column: string;
	target: Target;
	/** Set when the column is kept as an extra detail; `target` is then null. */
	extra?: KeptDetail;
	/** Set when the column names another item each row connects to; `target` is then null. */
	connect?: ConnectSettings;
}

/** The select value that keeps a column as an extra detail. */
export const KEEP = '__keep__';
/** The select value that connects each row to the item a column names. */
export const CONNECT = '__connect__';
/** An import connects at most this many columns, as the server allows. */
export const MAX_CONNECTED = 5;
/** An item can have at most this many extra details (design §16b). */
export const MAX_KEPT = 50;
/** The kinds a kept column can be, in the order they are offered. */
export const KEPT_KINDS: ExtraFieldKind[] = [
	'text',
	'number',
	'boolean',
	'date',
	'partialdate',
	'choice'
];

/** Every item has these, whatever its type. */
export const BUILT_IN_TARGETS: { value: 'name' | 'description' | 'tags'; label: string }[] = [
	{ value: 'name', label: 'Name' },
	{ value: 'description', label: 'Description' },
	{ value: 'tags', label: 'Tags' }
];

export interface TargetOption {
	value: string;
	label: string;
	disabled: boolean;
	/** Why it cannot be chosen. */
	hint?: string;
}

/** What a column can be matched to: the built-ins, then the type's fields. */
export function targetOptions(fields: ItemImportFieldResponse[]): TargetOption[] {
	return [
		...BUILT_IN_TARGETS.map((t) => ({ value: t.value, label: t.label, disabled: false })),
		...fields.map((f) => ({
			value: f.key,
			label: f.title,
			disabled: !f.importable,
			hint: f.importable ? undefined : (f.reason ?? undefined)
		}))
	];
}

/** Match a column to a target. A target belongs to one column, so any other column that had it loses it. */
export function assignTarget(
	choices: ColumnChoice[],
	column: string,
	target: Target
): ColumnChoice[] {
	return choices.map((choice) => {
		if (choice.column === column) return { column, target };
		if (target !== null && choice.target === target) return { ...choice, target: null };
		return choice;
	});
}

/** Keep a column as an extra detail, named after the column, instead of matching it. */
export function keepColumn(
	choices: ColumnChoice[],
	column: string,
	kind: ExtraFieldKind
): ColumnChoice[] {
	return choices.map((choice) =>
		choice.column === column ? { column, target: null, extra: { title: column, kind } } : choice
	);
}

function updateKept(
	choices: ColumnChoice[],
	column: string,
	change: Partial<KeptDetail>
): ColumnChoice[] {
	return choices.map((choice) => {
		if (choice.column !== column || !choice.extra) return choice;
		const extra: KeptDetail = { ...choice.extra, ...change };
		if (extra.key === undefined) delete extra.key;
		return { ...choice, extra };
	});
}

/** Rename a kept detail; with `joins`, it becomes that existing detail, key and kind. */
export const renameKept = (
	choices: ColumnChoice[],
	column: string,
	title: string,
	joins?: { key: string; kind: ExtraFieldKind }
) => updateKept(choices, column, joins ? { title, ...joins } : { title, key: undefined });

/** A different kind is a different field, so it no longer joins one. */
export const setKeptKind = (choices: ColumnChoice[], column: string, kind: ExtraFieldKind) =>
	updateKept(choices, column, { kind, key: undefined });

/** The extra details the items will get, in column order. */
export function keptDetails(choices: ColumnChoice[]): KeptDetail[] {
	return choices.flatMap((choice) =>
		choice.extra ? [{ title: choice.extra.title, kind: choice.extra.kind }] : []
	);
}

const NEW_CONNECTION: ConnectSettings = {
	relationship_type: null,
	item_type: null,
	row_end: 'source',
	on_missing: 'create'
};

/**
 * Connect each row to the item `column` names, or change how it connects. A column that is not
 * connected yet is refused once `MAX_CONNECTED` are, and `choices` come back as they were.
 */
export function connectColumn(
	choices: ColumnChoice[],
	column: string,
	settings: Partial<ConnectSettings> = {}
): ColumnChoice[] {
	const current = choices.find((c) => c.column === column)?.connect;
	if (!current && choices.filter((c) => c.connect).length >= MAX_CONNECTED) return choices;
	return choices.map((choice) =>
		choice.column === column
			? { column, target: null, connect: { ...NEW_CONNECTION, ...current, ...settings } }
			: choice
	);
}

/** Whether every connected column has its connection type and item type. */
export function connectionsReady(choices: ColumnChoice[]): boolean {
	return choices.every((c) => !c.connect || (c.connect.relationship_type && c.connect.item_type));
}

/** What the server takes for the connected columns that are ready. */
export function connectionEntries(choices: ColumnChoice[]): ConnectionColumnEntry[] {
	return choices.flatMap(({ column, connect }) =>
		connect?.relationship_type && connect.item_type
			? [
					{
						column,
						relationship_type: connect.relationship_type,
						item_type: connect.item_type,
						row_end: connect.row_end,
						on_missing: connect.on_missing
					}
				]
			: []
	);
}

/** "This row's item signed by the other item", and the other way round, from the type's label. */
export function rowEndOptions(relationship: {
	label: string;
	directional: boolean;
}): { value: ConnectionEnd; label: string }[] {
	const verb = relationship.label.charAt(0).toLowerCase() + relationship.label.slice(1);
	return [
		{ value: 'source', label: `This row's item ${verb} the other item` },
		{ value: 'target', label: `The other item ${verb} this row's item` }
	];
}

/** The items the connected columns name that going ahead would create. */
export function namedToCreate(plan: ImportPlan): string[] {
	// The import gives the items a column names `named-` refs and the rows `row-` refs.
	return plan.entities
		.filter((e) => e.kind === 'item' && e.action === 'create' && e.ref.startsWith('named-'))
		.map((e) => e.label);
}

/** An item cannot be made without a name. */
export function hasName(choices: ColumnChoice[]): boolean {
	return choices.some((choice) => choice.target === 'name');
}

export function choicesFrom(suggested: ColumnMappingEntry[]): ColumnChoice[] {
	return suggested.map((s) => ({ column: s.column, target: s.target ?? null }));
}

/**
 * What the server takes for the matching. Each kept detail gets a key from its name,
 * unique among the type's `fieldKeys`, the built-in targets and the other kept details.
 */
export function mappingEntries(choices: ColumnChoice[], fieldKeys: string[]): ColumnMappingEntry[] {
	const taken = new Set([...fieldKeys, ...BUILT_IN_TARGETS.map((t) => t.value)]);
	return choices.map(({ column, target, extra }) => {
		if (!extra) return { column, target };
		const key = extra.key ?? generateFieldKey(extra.title, taken);
		taken.add(key);
		return { column, target: null, extra: { key, title: extra.title.trim(), kind: extra.kind } };
	});
}

/** The columns that can recognise rows imported before: the name, a field, or a kept detail. */
export function keyColumns(choices: ColumnChoice[]): string[] {
	return choices
		.filter(
			(c) => c.extra || (c.target !== null && c.target !== 'description' && c.target !== 'tags')
		)
		.map((c) => c.column);
}

/** The field the server recognises rows by, for the key `column`: what it fills or is kept as. */
export function keyFieldFor(
	choices: ColumnChoice[],
	fieldKeys: string[],
	column: string | null
): string | null {
	const entry = mappingEntries(choices, fieldKeys).find((e) => e.column === column);
	return entry?.extra?.key ?? entry?.target ?? null;
}

/** The name people know each field by, keyed as a plan's `changed` lists it. */
export function fieldTitles(
	choices: ColumnChoice[],
	fields: ItemImportFieldResponse[]
): Record<string, string> {
	const titles: Record<string, string> = Object.fromEntries(
		BUILT_IN_TARGETS.map((t) => [t.value, t.label])
	);
	for (const f of fields) titles[`attributes.${f.key}`] = f.title;
	for (const e of mappingEntries(
		choices,
		fields.map((f) => f.key)
	)) {
		if (e.extra) titles[`attributes.${e.extra.key}`] = e.extra.title;
	}
	return titles;
}

export interface DeletedRow {
	key: string;
	label: string;
	/** Whether it is to be created again. */
	restored: boolean;
}

/**
 * Rows and connections deleted after an earlier import, ticked when `restore` brings them back:
 * the plan marks one left out as `deleted`, and creates one brought back.
 */
export function deletedRows(plan: ImportPlan, restore: string[]): DeletedRow[] {
	return plan.entities.flatMap((e) => {
		const key = e.source_key;
		if (!key) return [];
		const restored = e.action === 'create' && restore.includes(key);
		return e.deleted || restored ? [{ key, label: e.label, restored }] : [];
	});
}

/** How many items going ahead would add. */
export function itemsToAdd(plan: ImportPlan): number {
	return plan.entities.filter((e) => e.kind === 'item' && e.action === 'create').length;
}

function count(n: number): string {
	return n.toLocaleString('en-GB');
}

/** "Add 1,204 items". Item types have no plural form, so the type's name is not used. */
export function confirmText(n: number): string {
	return `Add ${count(n)} ${n === 1 ? 'item' : 'items'}`;
}

/** "1,204 rows, 6 columns". */
export function rowsAndColumns(
	inspection: Pick<ItemImportInspectionResponse, 'row_count' | 'headers'>
): string {
	const rows = inspection.row_count;
	const columns = inspection.headers.length;
	return `${count(rows)} ${rows === 1 ? 'row' : 'rows'}, ${count(columns)} ${columns === 1 ? 'column' : 'columns'}`;
}

export const DATE_ORDERS: { value: DayMonthOrder; label: string }[] = [
	{ value: 'day_first', label: 'Day first (19/08/2019 is 19 August)' },
	{ value: 'month_first', label: 'Month first (08/19/2019 is 19 August)' }
];

const ENCODING_NAMES: Record<CsvEncoding, string> = {
	utf_8: 'UTF-8',
	utf_16: 'UTF-16',
	windows_1252: 'Windows-1252'
};

/** An encoding as people know it, for "Read as ...". */
export function encodingName(encoding: CsvEncoding): string {
	return ENCODING_NAMES[encoding];
}

/** What a finished import added, as the toast says it. */
export function addedText(result: { items_added: number; connections_added: number }): string {
	const count = (n: number, one: string, many: string) =>
		`${n.toLocaleString('en-GB')} ${n === 1 ? one : many}`;
	const items = count(result.items_added, 'item', 'items');
	return result.connections_added > 0
		? `Added ${items} and ${count(result.connections_added, 'connection', 'connections')}`
		: `Added ${items}`;
}

/** What a queued import is waiting for: `ahead` imports run before it. */
export function waitingText(ahead: number | null | undefined): string {
	if (!ahead) return 'Starting soon…';
	return ahead === 1
		? 'Waiting for 1 other import to finish first'
		: `Waiting for ${ahead.toLocaleString('en-GB')} other imports to finish first`;
}
