import { uploadAndAttachMedia } from '$lib/api/client';

/** Uploads an image and attaches it to the node as its cover. */
export function uploadCover(nodeId: string, file: File) {
	return uploadAndAttachMedia({
		body: { file, target_type: 'node', target_id: nodeId, attribute_key: 'cover' }
	});
}
