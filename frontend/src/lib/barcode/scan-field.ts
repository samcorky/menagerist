/**
 * Where a scanned barcode goes: one text field of the item's type, chosen by the person, or a
 * new "Barcode" detail on the item when the type has no suitable field. Nothing else is filled;
 * looking the code up is separate.
 */
import { generateFieldKey } from '$lib/field-key';
import { isSection, itemsToSchema, schemaToItems } from '$lib/schema-editor-items';
import type { AttributesSchema, EditorField } from '$lib/schema-types';

export type ScanField = { key: string; label: string };

/** The choice that adds a new "Barcode" detail rather than filling one of the type's fields. */
export const NEW_BARCODE_DETAIL = '';

const NEW_DETAIL_LABEL = 'Barcode';

/** The type's single-line text fields, in the order the type shows them. */
export function scanFields(schema: AttributesSchema | null): ScanField[] {
	return schemaToItems(schema)
		.flatMap((item) => (isSection(item) ? item.fields : [item]))
		.filter((field) => field.kind === 'text' && !field.meta?.archived)
		.map(({ key, label }) => ({ key, label }));
}

/**
 * The field to choose before the person picks one, or null for a new Barcode detail.
 * Called with `scanFields(...)` each time the type changes.
 */
export function suggestScanField(fields: ScanField[]): string | null {
	for (const pattern of CODE_LABELS) {
		const match = fields.find((field) => pattern.test(field.label));
		if (match) return match.key;
	}
	return null;
}

/** Labels that say a field holds a code, most specific first. Word starts keep "Ocean" out. */
const CODE_LABELS = [/\bisbn/i, /\b(upc|ean|gtin)\b/i, /\bbar\s*code/i];

/** The attributes (and any new detail's schema) to save the scanned code with. */
export function scannedAttributes(
	code: string,
	fieldKey: string,
	schema: AttributesSchema | null
): { attributes: Record<string, string>; extraSchema: AttributesSchema | null } {
	if (fieldKey !== NEW_BARCODE_DETAIL)
		return { attributes: { [fieldKey]: code }, extraSchema: null };
	const key = generateFieldKey(NEW_DETAIL_LABEL, Object.keys(schema?.properties ?? {}));
	const field: EditorField = {
		key,
		label: NEW_DETAIL_LABEL,
		kind: 'text',
		required: false,
		options: [],
		subFields: []
	};
	return { attributes: { [key]: code }, extraSchema: itemsToSchema([field], {}) };
}
