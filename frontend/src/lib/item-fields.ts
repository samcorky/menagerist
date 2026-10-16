import { listItemFields } from '$lib/api/client';

/** A field individual items carry in their own overlay, with how many items use it. */
export type ItemField = { key: string; kind: string; label: string; count: number };

/** Read the per-item fields in use; null if the request fails. */
export async function fetchItemFields(): Promise<ItemField[] | null> {
	try {
		const result = await listItemFields();
		return result.error || !result.data ? null : result.data;
	} catch {
		return null;
	}
}
