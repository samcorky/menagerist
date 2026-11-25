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

type TypeLike = Pick<NodeTypeResponse, 'slug' | 'label'> & { parent?: string | null };

/**
 * The rows of the item type picker: the types you have items in first (biggest first, with their
 * counts), then the rest, narrowed by what was typed, and a Create row last when nothing has
 * exactly the typed name. Counting only your own items keeps the shared list from crowding it.
 *
 * A subtype in use shows with its parent (`crumb`), since its row stands alone. Of the rest, a
 * type with subtypes and its subtypes sit together under the parent's name, the parent first, so
 * a subtype needs no crumb there; the others follow as "Other item types". A search matches a
 * subtype by its parent's name too.
 */
export function buildTypeItems(args: {
	types: TypeLike[];
	/** Items per type slug, for the types in use. */
	counts: ReadonlyMap<string, number>;
	query: string;
	/** Offer "No item type" (only while nothing is typed). */
	allowClear: boolean;
	/** Offer a Create row for a name nothing has (default true). */
	allowCreate?: boolean;
}): ComboboxItem[] {
	const text = args.query.trim();
	const countOf = (type: TypeLike) => args.counts.get(type.slug) ?? 0;
	const byLabel = (a: TypeLike, b: TypeLike) => a.label.localeCompare(b.label);
	const bySlug = new Map(args.types.map((type) => [type.slug, type]));
	const parentOf = (type: TypeLike) => (type.parent ? bySlug.get(type.parent) : undefined);
	const parents = new Set(args.types.flatMap((type) => (parentOf(type) ? [type.parent!] : [])));
	// The type whose name heads this type's group, if it belongs to a family.
	const familyOf = (type: TypeLike) =>
		parentOf(type) ? type.parent! : parents.has(type.slug) ? type.slug : null;

	const used = args.types
		.filter((type) => countOf(type) > 0)
		.sort((a, b) => countOf(b) - countOf(a) || byLabel(a, b));
	const unused = args.types.filter((type) => countOf(type) === 0);

	const words = foldText(text).split(/\s+/).filter(Boolean);
	const matches = (type: TypeLike) => {
		const haystack = foldText(`${type.label} ${type.slug} ${parentOf(type)?.label ?? ''}`);
		return words.every((word) => haystack.includes(word));
	};

	const items: ComboboxItem[] = [];
	if (args.allowClear && !text) items.push({ value: NONE_VALUE, label: 'No item type' });
	for (const type of used.filter(matches)) {
		items.push({
			value: type.slug,
			label: type.label,
			crumb: parentOf(type)?.label,
			group: IN_USE,
			description: String(countOf(type))
		});
	}

	const families = new Map<string, TypeLike[]>();
	const others: TypeLike[] = [];
	for (const type of unused.filter(matches)) {
		const family = familyOf(type);
		if (family === null) others.push(type);
		else families.set(family, [...(families.get(family) ?? []), type]);
	}
	const heads = [...families.keys()].sort((a, b) => byLabel(bySlug.get(a)!, bySlug.get(b)!));
	for (const head of heads) {
		const members = families.get(head)!;
		// The parent leads its own group; its subtypes follow by name.
		members.sort((a, b) => Number(b.slug === head) - Number(a.slug === head) || byLabel(a, b));
		for (const type of members) {
			// The crumb is for the trigger; the list hides it under the heading that names it.
			items.push({
				value: type.slug,
				label: type.label,
				crumb: parentOf(type)?.label,
				group: bySlug.get(head)!.label
			});
		}
	}
	for (const type of others.sort(byLabel)) {
		items.push({ value: type.slug, label: type.label, group: OTHERS });
	}

	const exists = args.types.some(
		(type) => foldText(type.label) === foldText(text) || type.slug === slugify(text)
	);
	if (text && !exists && args.allowCreate !== false) {
		items.push({ value: CREATE_PREFIX + text, label: `Create “${text}”`, group: NEW });
	}
	return items;
}

/**
 * Every type as picker rows, with no counts: the types with no subtypes and no parent first, then
 * each parent and its subtypes under the parent's name, the parent leading its group. A subtype
 * carries its parent as the `crumb`, which the list hides under the heading that names it. For
 * the pickers that offer all types, such as the connection limits.
 */
export function groupTypeItems(types: TypeLike[]): ComboboxItem[] {
	const bySlug = new Map(types.map((type) => [type.slug, type]));
	const parentOf = (type: TypeLike) => (type.parent ? bySlug.get(type.parent) : undefined);
	const parents = new Set(types.flatMap((type) => (parentOf(type) ? [type.parent!] : [])));
	const byLabel = (a: TypeLike, b: TypeLike) => a.label.localeCompare(b.label);

	const items: ComboboxItem[] = types
		.filter((type) => !parentOf(type) && !parents.has(type.slug))
		.sort(byLabel)
		.map((type) => ({ value: type.slug, label: type.label }));
	const heads = [...parents].map((slug) => bySlug.get(slug)!).sort(byLabel);
	for (const head of heads) {
		const subtypes = types.filter((type) => type.parent === head.slug).sort(byLabel);
		items.push({ value: head.slug, label: head.label, group: head.label });
		for (const type of subtypes) {
			items.push({ value: type.slug, label: type.label, crumb: head.label, group: head.label });
		}
	}
	return items;
}

/** The label to create from a Create row's value, or null for a real type or no type. */
export function createdLabel(value: string): string | null {
	return value.startsWith(CREATE_PREFIX) ? value.slice(CREATE_PREFIX.length) : null;
}
