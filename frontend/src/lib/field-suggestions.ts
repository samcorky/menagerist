/**
 * Names of the extra details already on a type's items, offered when naming a new one. Choosing
 * one reuses that field's key and kind, so the new values join it and promoting it to the item
 * type later moves them all together (#573).
 */
import type { ItemField } from '$lib/item-fields';

const allowed = (field: ItemField, kinds?: readonly string[]) =>
	kinds === undefined || kinds.includes(field.kind);

/** Each name once, most used first, for the kinds that can be chosen. */
export function fieldNameSuggestions(fields: ItemField[], kinds?: readonly string[]): string[] {
	const names = [...fields]
		.filter((field) => allowed(field, kinds))
		.sort((a, b) => b.count - a.count)
		.map((field) => field.label);
	return [...new Set(names)];
}

/** The field a typed name belongs to, ignoring case; the most used one when several share it. */
export function matchItemField(
	name: string,
	fields: ItemField[],
	kinds?: readonly string[]
): ItemField | undefined {
	const wanted = name.trim().toLowerCase();
	if (!wanted) return undefined;
	return fields
		.filter((field) => allowed(field, kinds) && field.label.trim().toLowerCase() === wanted)
		.sort((a, b) => b.count - a.count)[0];
}
