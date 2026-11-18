import type {
	ColumnMappingEntry,
	CsvEncoding,
	ItemImportFieldResponse,
	ItemImportInspectionResponse
} from '$lib/api/client';
import type { ImportPlan } from '$lib/import-plan';

/** Where a column goes: `name`, `description`, `tags`, a field's key, or nowhere. */
export type Target = string | null;

export interface ColumnChoice {
	column: string;
	target: Target;
}

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

/** An item cannot be made without a name. */
export function hasName(choices: ColumnChoice[]): boolean {
	return choices.some((choice) => choice.target === 'name');
}

export function choicesFrom(suggested: ColumnMappingEntry[]): ColumnChoice[] {
	return suggested.map((s) => ({ column: s.column, target: s.target ?? null }));
}

/** The JSON text the server takes for the matching. */
export function mappingJson(choices: ColumnChoice[]): string {
	return JSON.stringify(choices);
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

const ENCODING_NAMES: Record<CsvEncoding, string> = {
	utf_8: 'UTF-8',
	utf_16: 'UTF-16',
	windows_1252: 'Windows-1252'
};

/** An encoding as people know it, for "Read as ...". */
export function encodingName(encoding: CsvEncoding): string {
	return ENCODING_NAMES[encoding];
}
