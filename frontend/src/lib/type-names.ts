/** The separator in a type's full name as plain text: "Memorabilia › Poster". */
export const PATH_SEPARATOR = ' › ';

type NamedType = { slug: string; label: string; parent?: string | null };

/**
 * `types` with each subtype straight after its parent, in the order given otherwise. A subtype
 * whose parent is not among them stays where it was. For a row of every type, such as filters.
 */
export function inFamilyOrder<T extends NamedType>(types: readonly T[]): T[] {
	const present = new Set(types.map((type) => type.slug));
	const under = new Map<string, T[]>();
	for (const type of types) {
		if (type.parent && present.has(type.parent)) {
			under.set(type.parent, [...(under.get(type.parent) ?? []), type]);
		}
	}
	const ordered: T[] = [];
	for (const type of types) {
		if (type.parent && present.has(type.parent)) continue;
		ordered.push(type, ...(under.get(type.slug) ?? []));
	}
	return ordered;
}

/**
 * Rows for item types (`options`, in the order given) split into groups for a select: the rows
 * whose type has no family come first with no heading, then one group per parent, headed by its
 * name, in the order each is first met. `isParent` marks the row for the parent type itself.
 * A row whose type is unknown has no family.
 */
export function groupByFamily<T extends { slug: string }>(
	options: readonly T[],
	types: readonly NamedType[]
): { heading: string | null; options: (T & { isParent: boolean })[] }[] {
	const bySlug = new Map(types.map((type) => [type.slug, type]));
	const hasSubtypes = new Set(
		types.flatMap((type) => (type.parent && bySlug.has(type.parent) ? [type.parent] : []))
	);
	const head = (slug: string) => {
		const parent = bySlug.get(slug)?.parent;
		return parent && bySlug.has(parent) ? parent : hasSubtypes.has(slug) ? slug : null;
	};
	const loose: (T & { isParent: boolean })[] = [];
	const families = new Map<string, (T & { isParent: boolean })[]>();
	for (const option of options) {
		const family = head(option.slug);
		const row = { ...option, isParent: family === option.slug };
		if (family === null) loose.push(row);
		else families.set(family, [...(families.get(family) ?? []), row]);
	}
	const groups = [...families].map(([slug, rows]) => ({
		heading: bySlug.get(slug)!.label,
		// The parent leads its group; the rest keep the order they came in.
		options: [...rows.filter((r) => r.isParent), ...rows.filter((r) => !r.isParent)]
	}));
	return loose.length > 0 ? [{ heading: null, options: loose }, ...groups] : groups;
}

/**
 * How to name an item type wherever it is shown as text. A subtype has a parent, and where room
 * allows it is shown with it, "Memorabilia › Poster" (`path`); in a card or a narrow row it is
 * "Poster" (`short`) with the full name as its tooltip. A screen reader hears "Poster, a subtype
 * of Memorabilia" (`spoken`). A top-level type, or a subtype whose parent is gone, is just its
 * name, and a slug no type has is shown as it is.
 */
export function typeNames(types: readonly NamedType[]) {
	const bySlug = new Map(types.map((type) => [type.slug, type]));
	const parentOf = (slug: string | null | undefined) => {
		const type = slug ? bySlug.get(slug) : undefined;
		return type?.parent ? bySlug.get(type.parent) : undefined;
	};
	const short = (slug: string | null | undefined) =>
		slug ? (bySlug.get(slug)?.label ?? slug) : '';
	return {
		/** The type's own name. */
		short,
		/** The type's name with its parent's before it. */
		path(slug: string | null | undefined) {
			const parent = parentOf(slug);
			return parent ? `${parent.label}${PATH_SEPARATOR}${short(slug)}` : short(slug);
		},
		/** The type's name as a screen reader should hear it. */
		spoken(slug: string | null | undefined) {
			const parent = parentOf(slug);
			return parent ? `${short(slug)}, a subtype of ${parent.label}` : short(slug);
		},
		/** The type a subtype belongs to, if it has one that still exists. */
		parentOf
	};
}
