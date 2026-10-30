import type { AttributesSchema } from '$lib/schema-types';

export type RetypeImpact = {
	/** Keys holding a value that no field of the new type or the item's own fields describes. */
	orphaned: string[];
	/** Item fields whose name the new type also defines; the two cannot be combined. */
	clashes: string[];
};

const isEmpty = (value: unknown) =>
	value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length);

/**
 * What changing an item's type would do to its values. Nothing is deleted: orphaned values stay
 * on the item and show as free-form rows, so this only tells the person which ones those are.
 */
export function retypeImpact(
	attributes: Record<string, unknown>,
	newTypeSchema: AttributesSchema | null,
	extraSchema: AttributesSchema | null
): RetypeImpact {
	const typeKeys = new Set(Object.keys(newTypeSchema?.properties ?? {}));
	const extraKeys = Object.keys(extraSchema?.properties ?? {});
	const clashes = extraKeys.filter((key) => typeKeys.has(key));
	const known = new Set([...typeKeys, ...extraKeys]);
	const orphaned = Object.entries(attributes)
		.filter(([key, value]) => !known.has(key) && !isEmpty(value))
		.map(([key]) => key);
	return { orphaned, clashes };
}
