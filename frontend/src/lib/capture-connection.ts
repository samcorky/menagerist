import type { EdgeTypeResponse } from '$lib/api/client';
import { allowsItemType, type ParentsByType } from '$lib/connection-limits';

/** One way a new item can be connected: a connection type, read from one end. */
export type ConnectionChoice = {
	/** Stable across loads, so a remembered choice can be found again. */
	key: string;
	typeSlug: string;
	/** The new item sits at the target end, so the picked item reads the connection. */
	reverse: boolean;
	/** How the new item reads it, e.g. "Stored in". */
	label: string;
	/** The item types the picked item may be; empty allows any. */
	pickedTypes: readonly string[];
};

export type RememberedConnection = {
	key: string;
	target: { id: string; name: string };
};

/**
 * Every way to read each connection type from the new item: by its label, and by its reverse
 * label where it has one ("Stored in" and "Contains").
 *
 * With `newItemType` given (null for an untyped item), only the readings its type allows are
 * kept: the new item sits at the source end of a forward reading and the target end of a reverse
 * one, and each connection type's limits apply to its own end.
 */
export function connectionChoices(
	types: EdgeTypeResponse[],
	newItemType?: string | null,
	parents?: ParentsByType
): ConnectionChoice[] {
	const filter = newItemType !== undefined;
	return types.flatMap((type) => {
		const choices: ConnectionChoice[] = [];
		if (!filter || allowsItemType(type.source_types, newItemType, parents)) {
			choices.push({
				key: `${type.slug}:forward`,
				typeSlug: type.slug,
				reverse: false,
				label: type.label,
				pickedTypes: type.target_types ?? []
			});
		}
		if (
			type.reverse_label &&
			(!filter || allowsItemType(type.target_types, newItemType, parents))
		) {
			choices.push({
				key: `${type.slug}:reverse`,
				typeSlug: type.slug,
				reverse: true,
				label: type.reverse_label,
				pickedTypes: type.source_types ?? []
			});
		}
		return choices;
	});
}

/**
 * The request that connects a new item to the picked one. `source_id` is the new item and the
 * connection runs to the picked item, or back from it for a reverse reading.
 */
export function connectionBody(choice: ConnectionChoice, newItemId: string, targetId: string) {
	return {
		source_id: newItemId,
		target_ids: [targetId],
		type: choice.typeSlug,
		reverse: choice.reverse
	};
}
