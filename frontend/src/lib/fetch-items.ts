import { listNodes, type NodeResponse } from '$lib/api/client';
import { PAGE_LIMIT } from '$lib/paging';

/**
 * The items with these ids, in any order. An id that is not an item you can see is left out, and
 * so are the ids of a request that failed, so a screen that only needs names to show still works.
 */
export async function fetchItemsById(ids: Iterable<string>): Promise<NodeResponse[]> {
	const wanted = [...new Set(ids)];
	const chunks: string[][] = [];
	for (let at = 0; at < wanted.length; at += PAGE_LIMIT) {
		chunks.push(wanted.slice(at, at + PAGE_LIMIT));
	}
	const results = await Promise.all(
		chunks.map((chunk) => listNodes({ query: { id: chunk, limit: PAGE_LIMIT } }))
	);
	return results.flatMap((result) => (result.error || !result.data ? [] : result.data));
}
