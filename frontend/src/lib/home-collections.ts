import type { CollectionResponse } from '$lib/api/client';
import { offlineController } from '$lib/offline.svelte';
import { OFFLINE_PREFERENCES, preferences, type PreferenceOutcome } from '$lib/preferences.svelte';
import type { Query } from '$lib/query/types';

// Which collections Home shows, in the order they were added: a hidden per-person setting, so
// the choice follows the person to every device. An id that no longer names a collection they
// can see is simply never shown (and comes back if the collection is restored).
const KEY = 'home.collections';

/** As many as the server keeps; "Show on Home" says so rather than failing. */
export const MAX_HOME_COLLECTIONS = 50;
export const HOME_FULL = `Home shows up to ${MAX_HOME_COLLECTIONS} collections. Take one off first.`;

/** How many of a collection's items Home shows before "View all". */
export const HOME_COLLECTION_ITEMS = 6;

export function homeCollectionIds(): string[] {
	const value = preferences.value(KEY);
	return Array.isArray(value) ? value : [];
}

/** Why the collection can't be put on or taken off Home now, or null when it can. */
export function homeToggleBlocked(id: string): string | null {
	if (offlineController.offline) return OFFLINE_PREFERENCES;
	const ids = homeCollectionIds();
	return !ids.includes(id) && ids.length >= MAX_HOME_COLLECTIONS ? HOME_FULL : null;
}

/** Show the collection on Home (last), or take it off. Applies at once; undone if not saved. */
export function toggleHomeCollection(id: string): Promise<PreferenceOutcome> {
	const blocked = homeToggleBlocked(id);
	if (blocked) return Promise.resolve({ ok: false, message: blocked });
	const ids = homeCollectionIds();
	return preferences.save(
		KEY,
		ids.includes(id) ? ids.filter((other) => other !== id) : [...ids, id]
	);
}

/** The chosen collections that still exist, in the order they were chosen. */
export function chosenCollections<T extends Pick<CollectionResponse, 'id'>>(
	ids: readonly string[],
	collections: readonly T[]
): T[] {
	const byId = new Map(collections.map((c) => [c.id, c]));
	return ids.flatMap((id) => byId.get(id) ?? []);
}

/** The collection's newest items: a collection condition reads manual and smart ones alike. */
export function homeCollectionQuery(id: string): Query {
	return {
		v: 1,
		where: { op: 'and', children: [{ kind: 'collection', mode: 'any', in: [id] }] },
		sort: [{ by: 'created', dir: 'desc' }]
	};
}
