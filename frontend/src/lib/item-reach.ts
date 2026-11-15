import {
	listNodePath,
	listNodeContents,
	type EdgeResponse,
	type EdgeTypeResponse,
	type NodeContentsEntryResponse,
	type NodeResponse
} from '$lib/api/client';

/** A relationship an item can be followed along, with the words the page uses for it. */
export type ReachChoice = { slug: string; label: string };

/** How many entries the Contains list asks for at a time. */
export const CONTENTS_PAGE_SIZE = 50;

/**
 * The directional relationships this item takes part in: `contents` where it holds other
 * items (read as the relationship's label, "Contains") and `inside` where other items hold
 * it (read as the reverse label, "Inside"). A relationship with no direction has neither.
 */
export function reachChoices(
	nodeId: string,
	edges: readonly EdgeResponse[],
	edgeTypes: readonly EdgeTypeResponse[]
): { contents: ReachChoice[]; inside: ReachChoice[] } {
	const bySlug = new Map(edgeTypes.map((et) => [et.slug, et]));
	const contents = new Map<string, ReachChoice>();
	const inside = new Map<string, ReachChoice>();
	for (const edge of edges) {
		const type = bySlug.get(edge.type);
		if (!type?.directional) continue;
		if (edge.source_id === nodeId && !contents.has(type.slug))
			contents.set(type.slug, { slug: type.slug, label: type.label });
		if (edge.target_id === nodeId && !inside.has(type.slug))
			inside.set(type.slug, { slug: type.slug, label: type.reverse_label ?? type.label });
	}
	return { contents: [...contents.values()], inside: [...inside.values()] };
}

/** The choice to show: the one picked if it is still on offer, otherwise the first. */
export function pickChoice(choices: readonly ReachChoice[], slug: string): ReachChoice | null {
	return choices.find((c) => c.slug === slug) ?? choices[0] ?? null;
}

/** Everything that holds the item, outermost first. Null when the request failed. */
export async function fetchPath(
	nodeId: string,
	relationship: string
): Promise<NodeResponse[] | null> {
	const { data, error } = await listNodePath({
		path: { node_id: nodeId },
		query: { relationship }
	});
	return error || !data ? null : data;
}

/** One page of what the item holds, any depth. Null when the request failed. */
export async function fetchContents(
	nodeId: string,
	relationship: string,
	after?: string
): Promise<NodeContentsEntryResponse[] | null> {
	const { data, error } = await listNodeContents({
		path: { node_id: nodeId },
		query: { relationship, depth: 25, limit: CONTENTS_PAGE_SIZE, ...(after ? { after } : {}) }
	});
	return error || !data ? null : data;
}

/** Whether another page may follow: a full page is taken to mean there is more. */
export function mayHaveMore(page: readonly unknown[]): boolean {
	return page.length >= CONTENTS_PAGE_SIZE;
}
