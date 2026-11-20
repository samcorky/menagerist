import type {
	ColumnMappingEntry,
	CsvEncoding,
	DayMonthOrder,
	ExtraFieldKind,
	ItemImportFieldResponse,
	ItemImportInspectionResponse
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

export interface ColumnChoice {
	column: string;
	target: Target;
	/** Set when the column is kept as an extra detail; `target` is then null. */
	extra?: KeptDetail;
}

/** The select value that keeps a column as an extra detail. */
export const KEEP = '__keep__';
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

/** An item cannot be made without a name. */
export function hasName(choices: ColumnChoice[]): boolean {
	return choices.some((choice) => choice.target === 'name');
}

export function choicesFrom(suggested: ColumnMappingEntry[]): ColumnChoice[] {
	return suggested.map((s) => ({ column: s.column, target: s.target ?? null }));
}

/**
 * The JSON text the server takes for the matching. Each kept detail gets a key from its name,
 * unique among the type's `fieldKeys`, the built-in targets and the other kept details.
 */
export function mappingJson(choices: ColumnChoice[], fieldKeys: string[]): string {
	const taken = new Set([...fieldKeys, ...BUILT_IN_TARGETS.map((t) => t.value)]);
	const entries: ColumnMappingEntry[] = choices.map(({ column, target, extra }) => {
		if (!extra) return { column, target };
		const key = extra.key ?? generateFieldKey(extra.title, taken);
		taken.add(key);
		return { column, target: null, extra: { key, title: extra.title.trim(), kind: extra.kind } };
	});
	return JSON.stringify(entries);
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
