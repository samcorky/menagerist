import type { EdgeTypeResponse } from '$lib/api/client';

/** One way a new item can be connected: a connection type, read from one end. */
export type ConnectionChoice = {
	/** Stable across loads, so a remembered choice can be found again. */
	key: string;
	typeSlug: string;
	/** The new item sits at the target end, so the picked item reads the connection. */
	reverse: boolean;
	/** How the new item reads it, e.g. "Stored in". */
	label: string;
};

export type RememberedConnection = {
	key: string;
	target: { id: string; name: string };
};

/**
 * Every way to read each connection type from the new item: by its label, and by its reverse
 * label where it has one ("Stored in" and "Contains").
 */
export function connectionChoices(types: EdgeTypeResponse[]): ConnectionChoice[] {
	return types.flatMap((type) => {
		const choices: ConnectionChoice[] = [
			{ key: `${type.slug}:forward`, typeSlug: type.slug, reverse: false, label: type.label }
		];
		if (type.reverse_label) {
			choices.push({
				key: `${type.slug}:reverse`,
				typeSlug: type.slug,
				reverse: true,
				label: type.reverse_label
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
