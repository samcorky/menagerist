import type { PropertyMeta } from '$lib/schema-meta';

// Which kinds a saved field may be switched to. Everything not listed needs
// "Replace field" (a new field, with the old one archived), because a stored value
// cannot be turned into a stricter type without losing or rejecting data.
const TO_TEXT = ['text', 'longtext'];

const ALLOWED: Record<string, string[]> = {
	text: ['text', 'longtext'],
	longtext: ['longtext', 'text'],
	number: ['number', 'rating', 'duration', ...TO_TEXT],
	rating: ['rating', 'number', ...TO_TEXT],
	duration: ['duration', 'number', ...TO_TEXT],
	boolean: ['boolean', ...TO_TEXT],
	// Every full date is a valid partial date, so it may be loosened (not the reverse).
	date: ['date', 'partialdate', ...TO_TEXT],
	partialdate: ['partialdate', ...TO_TEXT],
	choice: ['choice', ...TO_TEXT],
	group: ['group'],
	// Array-shaped like list and checklist: it cannot become text without a shape change.
	multichoice: ['multichoice'],
	// Object-shaped like `group`: its stored value is `{value, unit}`, not a scalar, so it
	// cannot become text without a shape change. Falls back to this anyway if omitted
	// (`ALLOWED[original] ?? [original]`), but listed explicitly like every other kind.
	quantity: ['quantity'],
	// Object-shaped like quantity: its stored value is `{value, currency}`, not a scalar.
	money: ['money'],
	// Plain strings, same as date: can degrade to text without losing data.
	url: ['url', ...TO_TEXT],
	email: ['email', ...TO_TEXT],
	phone: ['phone', ...TO_TEXT]
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
	if (original === 'number' && kind === 'duration') {
		return 'Values that are negative or not whole seconds will show an error when edited.';
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
