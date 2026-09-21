import type { AttributeRow } from '$lib/attribute-rows';
import type { AttributesSchema } from '$lib/schema-types';

/** Longest name of a detail, and most details on one item. The server enforces the same limits. */
export const MAX_CUSTOM_NAME_LENGTH = 100;
export const MAX_CUSTOM_DETAILS = 50;

/**
 * Whether a row is a detail: a value under a name the type has no field for. Rows added with
 * "Add detail" stay details even when their name is (wrongly) the same as a field.
 */
export function isDetailRow(row: AttributeRow, schema: AttributesSchema | null | undefined) {
	return row.extra === true || !(schema && Object.hasOwn(schema.properties, row.key));
}

function hasValue(row: AttributeRow): boolean {
	if (typeof row.value !== 'string') return true;
	if (row.kind === 'boolean' && row.value === 'false') return false;
	return row.value.trim() !== '';
}

export type DetailProblems = {
	/** Message per problem row; a row with a problem blocks saving. */
	errors: Map<AttributeRow, string>;
	blocking: boolean;
};

/**
 * Problems with the names of an item's details. They block saving because two rows with the same
 * name would silently overwrite each other, and a value with no name would be dropped.
 * A name may not match any field of the type, including removed ones, ignoring case.
 */
export function customDetailProblems(
	rows: AttributeRow[],
	schema: AttributesSchema | null | undefined
): DetailProblems {
	const fieldNames = new Set(Object.keys(schema?.properties ?? {}).map((k) => k.toLowerCase()));
	const details = rows.filter((row) => isDetailRow(row, schema));
	const counts = new Map<string, number>();
	for (const row of details) {
		const name = row.key.trim().toLowerCase();
		if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
	}

	const errors = new Map<AttributeRow, string>();
	for (const row of details) {
		const name = row.key.trim();
		if (name === '') {
			if (hasValue(row)) errors.set(row, 'Give this detail a name.');
		} else if (fieldNames.has(name.toLowerCase()) || (counts.get(name.toLowerCase()) ?? 0) > 1) {
			errors.set(row, 'This name is already in use.');
		} else if (row.extra && name.length > MAX_CUSTOM_NAME_LENGTH) {
			errors.set(row, `Names can be at most ${MAX_CUSTOM_NAME_LENGTH} characters.`);
		}
	}
	return { errors, blocking: errors.size > 0 };
}

/** Whether another detail may be added. */
export function canAddDetail(
	rows: AttributeRow[],
	schema: AttributesSchema | null | undefined
): boolean {
	return rows.filter((row) => isDetailRow(row, schema)).length < MAX_CUSTOM_DETAILS;
}

/** Text for showing a detail's value: yes/no in words, and unchanged values as compact JSON. */
export function displayDetailValue(row: AttributeRow): string {
	if (row.raw !== undefined && (row.kind === 'json' || typeof row.value !== 'string')) {
		return JSON.stringify(row.raw);
	}
	if (typeof row.value !== 'string') return JSON.stringify(row.value);
	if (row.kind === 'boolean') return row.value === 'true' ? 'Yes' : 'No';
	return row.value;
}
