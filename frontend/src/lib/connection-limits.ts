import type { EdgeTypeResponse } from '$lib/api/client';

type Limits = Pick<EdgeTypeResponse, 'source_types' | 'target_types'>;

/**
 * Whether an item of `itemType` may sit at an end limited to `allowed`. No limit allows any
 * item, untyped ones included; a limit allows only the listed types, so never an untyped item.
 * The server enforces the same rule; this keeps the pickers in step with it.
 */
export function allowsItemType(
	allowed: readonly string[] | undefined,
	itemType: string | null | undefined
): boolean {
	if (!allowed || allowed.length === 0) return true;
	return itemType != null && allowed.includes(itemType);
}

/** Whether items of these types may be joined by the connection type (an unknown one fits). */
export function fitsLimits(
	type: Limits | undefined,
	sourceType: string | null | undefined,
	targetType: string | null | undefined
): boolean {
	if (!type) return true;
	return (
		allowsItemType(type.source_types, sourceType) && allowsItemType(type.target_types, targetType)
	);
}

/**
 * The limits as short text, "Book, Comic → Person", or null with none. `labels` maps an item
 * type's slug to its name; a slug with no entry (a deleted type) shows as it is.
 */
export function describeLimits(type: Limits, labels?: ReadonlyMap<string, string>): string | null {
	if (type.source_types.length === 0 && type.target_types.length === 0) return null;
	const end = (slugs: readonly string[]) =>
		slugs.length === 0 ? 'any' : slugs.map((s) => labels?.get(s) ?? s).join(', ');
	return `${end(type.source_types)} → ${end(type.target_types)}`;
}
