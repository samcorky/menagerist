import { listNodes, type NodeResponse } from '$lib/api/client';
import { PAGE_LIMIT, readPages } from '$lib/paging';

/**
 * Up to `max` items, a page at a time. A failed page ends the read with what was loaded, so a
 * screen that only needs names to show still works.
 */
export async function fetchItems(max = 500): Promise<NodeResponse[]> {
	const { rows } = await readPages<NodeResponse>(
		(after) => listNodes({ query: { after, limit: PAGE_LIMIT } }),
		{ maxRows: max }
	);
	return rows;
}
