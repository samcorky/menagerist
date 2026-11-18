// Server-renders NodeCover: a list that already knows the cover must not ask for it again.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createRawSnippet, type ComponentProps } from 'svelte';
import { render } from 'svelte/server';

const { listNodeMedia } = vi.hoisted(() => ({ listNodeMedia: vi.fn() }));
vi.mock('$lib/api/client', () => ({ listNodeMedia }));

import NodeCover from '$lib/components/node-cover.svelte';

const fallback = createRawSnippet(() => ({ render: () => '<i data-testid="fallback"></i>' }));

function html(props: Partial<ComponentProps<typeof NodeCover>> = {}): string {
	return render(NodeCover, { props: { nodeId: 'n1', children: fallback, ...props } }).body;
}

beforeEach(() => {
	listNodeMedia.mockReset();
	listNodeMedia.mockResolvedValue({ data: [] });
});

describe('NodeCover with a thumbnail the list supplied', () => {
	it('draws the thumbnail, lazily, without asking for the item media', () => {
		const out = html({ thumbnailUrl: '/api/v1/media/a/thumbnail', class: 'size-12' });
		expect(out).toMatch(/<img[^>]*src="\/api\/v1\/media\/a\/thumbnail"/);
		expect(out).toContain('loading="lazy"');
		expect(out).toContain('size-12');
		expect(listNodeMedia).not.toHaveBeenCalled();
	});

	it('shows the fallback for an item the list says has no cover, without a request', () => {
		const out = html({ thumbnailUrl: null });
		expect(out).toContain('data-testid="fallback"');
		expect(out).not.toContain('<img');
		expect(listNodeMedia).not.toHaveBeenCalled();
	});
});

describe('NodeCover on its own', () => {
	it('asks for the item media when no thumbnail is supplied', () => {
		html();
		expect(listNodeMedia).toHaveBeenCalledWith({ path: { node_id: 'n1' } });
	});
});
