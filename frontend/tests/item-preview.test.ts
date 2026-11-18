import { describe, expect, it } from 'vitest';
import { itemPreviewFor, rememberItemPreview } from '$lib/item-preview';

const item = { id: 'a', name: 'Alien', cover_thumbnail_url: '/api/v1/media/m/thumbnail' };

describe('item preview', () => {
	it('hands back the item that was clicked, for that item only', () => {
		rememberItemPreview(item);
		expect(itemPreviewFor('a')).toEqual({
			id: 'a',
			name: 'Alien',
			cover_thumbnail_url: '/api/v1/media/m/thumbnail'
		});
		expect(itemPreviewFor('b')).toBeNull();
	});

	it('keeps only the latest click', () => {
		rememberItemPreview(item);
		rememberItemPreview({ id: 'c', name: 'Aliens' });
		expect(itemPreviewFor('a')).toBeNull();
		expect(itemPreviewFor('c')).toEqual({ id: 'c', name: 'Aliens', cover_thumbnail_url: null });
	});
});
