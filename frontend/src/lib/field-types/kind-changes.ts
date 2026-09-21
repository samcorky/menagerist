import type { PropertyMeta } from '$lib/schema-meta';

// Which kinds a saved field may be switched to. Everything not listed needs
// "Replace field" (a new field, with the old one archived), because a stored value
// cannot be turned into a stricter type without losing or rejecting data.
const TO_TEXT = ['text', 'longtext'];

const ALLOWED: Record<string, string[]> = {
	text: ['text', 'longtext'],
	longtext: ['longtext', 'text'],
	number: ['number', 'rating', ...TO_TEXT],
	rating: ['rating', 'number', ...TO_TEXT],
	boolean: ['boolean', ...TO_TEXT],
	date: ['date', ...TO_TEXT],
	choice: ['choice', ...TO_TEXT],
	group: ['group']
};

/**
 * Filter `available` kinds to those a field saved as `original` may become. A field that has
 * never been saved (`original` undefined) can be any kind. Unknown kinds keep only themselves.
 */
export function allowedKinds(original: string | undefined, available: string[]): string[] {
	if (original === undefined) return available;
	const allowed = ALLOWED[original] ?? [original];
	return available.filter((kind) => allowed.includes(kind));
}

/** Warning to show after switching a saved field's kind, or null. */
export function kindChangeWarning(original: string | undefined, kind: string): string | null {
	if (original === 'number' && kind === 'rating') {
		return 'Values outside 1 to 5 will show an error when edited.';
	}
	return null;
}

/** Switch a field's kind, dropping the display and config settings that belong to the old kind. */
export function changeKind<T extends { kind: string; meta?: PropertyMeta }>(
	field: T,
	kind: string
): T {
	if (field.kind === kind) return field;
	const meta = { ...field.meta };
	delete meta.display;
	delete meta.config;
	const next: T & { config?: unknown } = { ...field, kind, meta };
	delete next.config;
	return next;
}
