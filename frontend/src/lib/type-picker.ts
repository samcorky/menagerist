import type { NodeTypeResponse } from '$lib/api/client';
import type { ComboboxItem } from '$lib/components/ui/combobox/combobox';
import { foldText } from '$lib/fold-text';
import { slugify } from '$lib/utils.js';

/** The value for "no item type". */
export const NONE_VALUE = '';
/** A "Create …" row's value is this prefix followed by the typed label. */
export const CREATE_PREFIX = 'create:';

const IN_USE = 'In use';
const OTHERS = 'Other item types';
const NEW = 'New item type';

type TypeLike = Pick<NodeTypeResponse, 'slug' | 'label'>;

/**
 * The rows of the item type picker: the types you have items in first (biggest first, with their
 * counts), then the rest, narrowed by what was typed, and a Create row last when nothing has
 * exactly the typed name. Counting only your own items keeps the shared list from crowding it.
 */
export function buildTypeItems(args: {
	types: TypeLike[];
	/** Items per type slug, for the types in use. */
	counts: ReadonlyMap<string, number>;
	query: string;
	/** Offer "No item type" (only while nothing is typed). */
	allowClear: boolean;
}): ComboboxItem[] {
	const text = args.query.trim();
	const countOf = (type: TypeLike) => args.counts.get(type.slug) ?? 0;
	const byLabel = (a: TypeLike, b: TypeLike) => a.label.localeCompare(b.label);
	const used = args.types
		.filter((type) => countOf(type) > 0)
		.sort((a, b) => countOf(b) - countOf(a) || byLabel(a, b));
	const others = args.types.filter((type) => countOf(type) === 0).sort(byLabel);

	const words = foldText(text).split(/\s+/).filter(Boolean);
	const matches = (type: TypeLike) => {
		const haystack = foldText(`${type.label} ${type.slug}`);
		return words.every((word) => haystack.includes(word));
	};

	const items: ComboboxItem[] = [];
	if (args.allowClear && !text) items.push({ value: NONE_VALUE, label: 'No item type' });
	for (const type of used.filter(matches)) {
		items.push({
			value: type.slug,
			label: type.label,
			group: IN_USE,
			description: String(countOf(type))
		});
	}
	for (const type of others.filter(matches)) {
		items.push({ value: type.slug, label: type.label, group: OTHERS });
	}

	const exists = args.types.some(
		(type) => foldText(type.label) === foldText(text) || type.slug === slugify(text)
	);
	if (text && !exists) {
		items.push({ value: CREATE_PREFIX + text, label: `Create “${text}”`, group: NEW });
	}
	return items;
}

/** The label to create from a Create row's value, or null for a real type or no type. */
export function createdLabel(value: string): string | null {
	return value.startsWith(CREATE_PREFIX) ? value.slice(CREATE_PREFIX.length) : null;
}
