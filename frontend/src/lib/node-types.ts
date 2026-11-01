import { listNodeTypes, type NodeTypeResponse } from '$lib/api/client';

export const NODE_TYPES_PAGE_SIZE = 100;

/** Read every item type, following the Link header's next cursor; null if any page fails. */
export async function fetchAllNodeTypes(): Promise<NodeTypeResponse[] | null> {
	const all: NodeTypeResponse[] = [];
	let after: string | undefined;
	for (;;) {
		const result = await listNodeTypes({ query: { after, limit: NODE_TYPES_PAGE_SIZE } });
		if (result.error || !result.data) return null;
		all.push(...result.data);
		const hasNext = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		if (!hasNext || result.data.length === 0) return all;
		after = result.data[result.data.length - 1].id;
	}
}
