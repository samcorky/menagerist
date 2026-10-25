import { countNodes } from '$lib/api/client';

/** The filters the list and `GET /node/count` share. */
export type CountFilters = { q: string; type: string | null };

/** The exact number of matches, or null when the count could not be fetched. */
export async function fetchExactCount(filters: CountFilters): Promise<number | null> {
	try {
		const result = await countNodes({
			query: { q: filters.q || undefined, type: filters.type ?? undefined }
		});
		return result.error || !result.data ? null : result.data.count;
	} catch {
		return null;
	}
}

/**
 * Runs the exact count for a capped search and applies it only if it is still the latest
 * request, so a late answer for older filters is dropped.
 */
export function createCountTracker(
	fetchCount: (filters: CountFilters) => Promise<number | null> = fetchExactCount
) {
	let seq = 0;
	return {
		/** Invalidates any count still in flight. */
		cancel() {
			seq++;
		},
		async run(filters: CountFilters, apply: (exact: number) => void): Promise<void> {
			const mine = ++seq;
			const exact = await fetchCount(filters);
			if (mine === seq && exact !== null) apply(exact);
		}
	};
}
