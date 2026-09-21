import type { EditorField } from '$lib/schema-types';

/** Mark a saved field as archived: its data is kept, but forms no longer show it. */
export function archiveField(field: EditorField): EditorField {
	const { highlight: _highlight, ...rest } = field;
	return { ...rest, meta: { ...field.meta, archived: true } };
}

/** Undo `archiveField`. */
export function restoreField(field: EditorField): EditorField {
	const meta = { ...field.meta };
	delete meta.archived;
	return { ...field, meta };
}
