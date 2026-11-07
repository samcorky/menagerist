import type { DuplicateNodeRequest } from '$lib/api/client';

/** What a copy takes from the original besides its details and tags. */
export type DuplicateChoices = {
	connections: boolean;
	media: boolean;
	cover: boolean;
	collections: boolean;
};

/** Connections, media and the cover start off; a copy usually joins the same collections. */
export const DEFAULT_DUPLICATE_CHOICES: DuplicateChoices = {
	connections: false,
	media: false,
	cover: false,
	collections: true
};

/** The name offered for a copy of `name`. */
export function defaultCopyName(name: string): string {
	return `Copy of ${name}`;
}

/** The request body for copying an item under `name` with the given choices. */
export function duplicateBody(name: string, choices: DuplicateChoices): DuplicateNodeRequest {
	return {
		name: name.trim(),
		copy_relationships: choices.connections,
		copy_media: choices.media,
		copy_cover: choices.cover,
		copy_collections: choices.collections
	};
}
