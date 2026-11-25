import { archivedKeys } from '$lib/schema-meta';

type AppearanceType = {
	slug: string;
	parent?: string | null;
	icon?: string | null;
	colour?: string | null;
};

/**
 * The icon and colour to draw an item type with. A subtype takes its parent's until it sets its
 * own, each separately, so a subtype with just an icon keeps its parent's colour. A type with
 * nothing set, an unknown one and no type at all have none.
 */
export function appearanceOf(
	slug: string | null | undefined,
	types: readonly AppearanceType[]
): { icon: string | null; colour: string | null } {
	const type = slug ? types.find((t) => t.slug === slug) : undefined;
	const parent = type?.parent ? types.find((t) => t.slug === type.parent) : undefined;
	return {
		icon: type?.icon ?? parent?.icon ?? null,
		colour: type?.colour ?? parent?.colour ?? null
	};
}

type SchemaType = {
	attributes_schema?: { properties?: Record<string, unknown> } | Record<string, unknown> | null;
	effective_schema?: { properties?: Record<string, unknown> } | Record<string, unknown> | null;
};

const keysOf = (schema: SchemaType['attributes_schema']): string[] => {
	const properties = (schema as { properties?: Record<string, unknown> } | null | undefined)
		?.properties;
	return properties ? Object.keys(properties) : [];
};

/**
 * The types a type may be made a subtype of: the top-level ones except itself, in the order
 * given. A type that already has subtypes cannot be a subtype (one level only), so it is `lockedBy`
 * those subtypes and the picker explains why instead of offering a choice.
 */
export function parentChoices<T extends { slug: string; parent?: string | null }>(
	types: readonly T[],
	editing: { slug: string } | null
): { options: T[]; lockedBy: T[] } {
	return {
		options: types.filter((t) => !t.parent && t.slug !== editing?.slug),
		lockedBy: editing ? types.filter((t) => t.parent === editing.slug) : []
	};
}

/** The live fields a parent type gives its subtypes, each as its key and the name it shows. */
export function inheritedFieldRows(
	parent: { attributes_schema?: SchemaType['attributes_schema'] } | null | undefined
): { key: string; label: string }[] {
	const schema = (parent?.attributes_schema ?? null) as {
		properties?: Record<string, Record<string, unknown>>;
	} | null;
	const archived = archivedKeys(schema);
	return Object.entries(schema?.properties ?? {})
		.filter(([key]) => !archived.has(key))
		.map(([key, prop]) => ({
			key,
			label: typeof prop.title === 'string' && prop.title ? prop.title : key
		}));
}

/**
 * What a subtype's form needs to tag the fields it gets from its parent: those keys and the
 * parent's name. Null when the type has no parent that still exists, or nothing inherited.
 */
export function inheritedFromParent(
	type: (SchemaType & { parent?: string | null }) | null | undefined,
	types: readonly { slug: string; label: string }[]
): { keys: string[]; label: string } | null {
	const parent = type?.parent ? types.find((t) => t.slug === type.parent) : undefined;
	const keys = inheritedKeys(type);
	return parent && keys.length > 0 ? { keys, label: parent.label } : null;
}

/**
 * The keys of the fields a subtype uses but its parent defines: the effective schema's keys that
 * the type's own schema does not have, in the order the type uses them. A type with no parent
 * has none. No server change is needed since both schemas are on the type.
 */
export function inheritedKeys(type: SchemaType | null | undefined): string[] {
	if (!type?.effective_schema) return [];
	const own = new Set(keysOf(type.attributes_schema));
	return keysOf(type.effective_schema).filter((key) => !own.has(key));
}
