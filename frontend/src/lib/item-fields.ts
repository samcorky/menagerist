import { listItemFields, listPresets } from '$lib/api/client';
import type { FieldDefinition } from '$lib/presets';
import { SAVED_FIELDS_CAP, type SavedField } from '$lib/query/fields';

/** A field individual items carry in their own overlay, with how many items use it. */
export type ItemField = { key: string; kind: string; label: string; count: number };

/** Read the per-item fields in use; null if the request fails. */
export async function fetchItemFields(): Promise<ItemField[] | null> {
	try {
		const result = await listItemFields();
		return result.error || !result.data ? null : result.data;
	} catch {
		return null;
	}
}

/** Read the person's saved single fields for the search builder; null if the request fails. */
export async function fetchSavedFields(): Promise<SavedField[] | null> {
	try {
		const result = await listPresets({ query: { kind: 'field', limit: SAVED_FIELDS_CAP } });
		if (result.error || !result.data) return null;
		return result.data.flatMap((p) => {
			const property = (p.definition as Partial<FieldDefinition>).property;
			return property ? [{ id: p.id, label: p.label, property }] : [];
		});
	} catch {
		return null;
	}
}
