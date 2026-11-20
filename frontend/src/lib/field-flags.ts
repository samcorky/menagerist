/**
 * Yes/no settings an item type's field can carry in its metadata (`PropertyMeta`), offered in the
 * type editor only for the kinds they make sense for.
 */
import type { EditorField } from '$lib/schema-types';

export type FieldFlag = {
	member: 'capture' | 'barcode';
	label: string;
	/** Shown as a chip under the field while the flag is on. */
	chip: string;
	kinds: ReadonlySet<string>;
};

/** Kinds whose input fits on one row, so they can be filled in from quick capture. */
export const QUICK_CAPTURE_KINDS: ReadonlySet<string> = new Set([
	'text',
	'number',
	'boolean',
	'choice',
	'multichoice',
	'date',
	'partialdate',
	'rating',
	'money',
	'quantity',
	'duration',
	'url',
	'email',
	'phone'
]);

export const FIELD_FLAGS: readonly FieldFlag[] = [
	{
		member: 'capture',
		label: 'Show in quick capture',
		chip: 'Quick capture',
		kinds: QUICK_CAPTURE_KINDS
	},
	{ member: 'barcode', label: 'Takes barcodes', chip: 'Barcodes', kinds: new Set(['text']) }
];

/** The flags offered for a field of this kind. */
export function flagsFor(kind: string): FieldFlag[] {
	return FIELD_FLAGS.filter((flag) => flag.kinds.has(kind));
}

/** A copy of `field` with the flag switched on, or removed when switched off. */
export function setFlag(field: EditorField, member: FieldFlag['member'], on: boolean): EditorField {
	const meta = { ...field.meta };
	if (on) meta[member] = true;
	else delete meta[member];
	return { ...field, meta };
}

/** Chips for what is switched on in the field's menu: Required, then its flags. */
export function fieldChips(field: EditorField): string[] {
	const flags = flagsFor(field.kind).filter((flag) => field.meta?.[flag.member] === true);
	return [...(field.required ? ['Required'] : []), ...flags.map((flag) => flag.chip)];
}
