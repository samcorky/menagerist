import type { CollectionResponse } from '$lib/api/client';
import type { Query } from '$lib/query/types';
import { readList, writeList } from '$lib/remembered';

// Which collections Home shows, in the order they were added. Remembered per device, like
// Home's open sections; an id that no longer names a collection is simply never shown.
const KEY = 'home-collections';

/** How many of a collection's items Home shows before "View all". */
export const HOME_COLLECTION_ITEMS = 6;

export function homeCollectionIds(): string[] {
	return readList(KEY);
}

/** Show the collection on Home (last), or take it off; returns whether it is now shown. */
export function toggleHomeCollection(id: string): boolean {
	const ids = homeCollectionIds();
	const shown = !ids.includes(id);
	writeList(KEY, shown ? [...ids, id] : ids.filter((other) => other !== id));
	return shown;
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
