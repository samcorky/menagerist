import type { NodeResponse } from '$lib/api/client';

/** What a list already knows of an item, enough to draw the start of its page. */
export type ItemPreview = {
	id: string;
	name: string;
	cover_thumbnail_url: string | null;
};

// Held only until the next click: the page it was kept for reads it while it loads.
let held: ItemPreview | null = null;

/** Keeps the title and cover thumbnail of the item being opened, so its page need not wait. */
export function rememberItemPreview(
	item: Pick<NodeResponse, 'id' | 'name' | 'cover_thumbnail_url'>
): void {
	held = { id: item.id, name: item.name, cover_thumbnail_url: item.cover_thumbnail_url ?? null };
}

/** The preview kept for `id`, or null if the person did not come from a list. */
export function itemPreviewFor(id: string): ItemPreview | null {
	return held?.id === id ? held : null;
}
