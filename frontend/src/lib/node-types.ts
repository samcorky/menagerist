import { listNodeTypes, type NodeTypeResponse } from '$lib/api/client';
import { readPages } from '$lib/paging';
import type { AttributesSchema } from '$lib/schema-types';

export const NODE_TYPES_PAGE_SIZE = 100;

/**
 * The fields items of a type use and show: a subtype's parent's followed by its own, as the
 * server resolves them. `attributes_schema` stays what the type itself defines, which is what
 * the type editor edits. Falls back to that for a response without an effective schema.
 */
export function effectiveSchema(
	type: Pick<NodeTypeResponse, 'attributes_schema' | 'effective_schema'> | null | undefined
): AttributesSchema | null {
	return (type?.effective_schema ?? type?.attributes_schema ?? null) as AttributesSchema | null;
}

/** Read every item type, following the Link header's next cursor; null if any page fails. */
export async function fetchAllNodeTypes(): Promise<NodeTypeResponse[] | null> {
	const { rows, ok } = await readPages<NodeTypeResponse>((after) =>
		listNodeTypes({ query: { after, limit: NODE_TYPES_PAGE_SIZE } })
	);
	return ok ? rows : null;
}
