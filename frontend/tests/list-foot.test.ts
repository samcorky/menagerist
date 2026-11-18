// Server-renders ListFoot: the foot of a paging list must always say what it is doing (#588).
import { describe, expect, it, vi } from 'vitest';
import { render } from 'svelte/server';
import type { ComponentProps } from 'svelte';

// The icons render here, so the null stubs in tests/mocks/lucide-svelte.ts will not do.
vi.mock('@lucide/svelte', async () => ({
	RefreshCw: (await import('./mocks/noop.svelte')).default
}));
vi.mock('@lucide/svelte/icons/loader-2', async () => ({
	default: (await import('./mocks/noop.svelte')).default
}));

import ListFoot from '$lib/components/list-foot.svelte';

function html(props: Partial<ComponentProps<typeof ListFoot>> = {}): string {
	return render(ListFoot, {
		props: { loading: false, hasMore: false, rows: 5, noun: 'item', onload: () => {}, ...props }
	}).body;
}

describe('ListFoot', () => {
	it('names the count at the end of a list', () => {
		expect(html({ rows: 50, total: 1204 })).toContain('1,204 items');
	});

	it('says nothing while more pages are still to come', () => {
		const body = html({ hasMore: true });
		expect(body).not.toContain('5 items');
		expect(body).not.toContain("couldn't load");
		expect(body).not.toContain('data-testid="list-end"');
	});

	it('leaves an empty list to its own empty state', () => {
		expect(html({ rows: 0 })).not.toContain('0 items');
	});

	it('offers a retry for a page that would not load', () => {
		const body = html({ hasMore: true, failed: true, onretry: () => {} });
		expect(body).toContain("We couldn't load any more.");
		expect(body).toContain('Try again');
	});

	it('states the failure even with no retry handler', () => {
		const body = html({ hasMore: true, failed: true });
		expect(body).toContain("We couldn't load any more.");
		expect(body).not.toContain('Try again');
	});

	it('announces the end politely, in a live region', () => {
		expect(html({ rows: 50, total: 1204 })).toMatch(
			/role="status" aria-live="polite">[^<]*1,204 items/
		);
	});

	it('announces loading more as plain words, not as the spinner', () => {
		const body = html({ hasMore: true, loading: true, rows: 10 });
		expect(body).toMatch(/role="status" aria-live="polite">\s*Loading more…/);
	});

	it('hides the sentinel from the reader, which the live region speaks for', () => {
		expect(html({ hasMore: true })).toContain('aria-hidden="true"');
	});

	it('adds a flavour line beside the count on a long list', () => {
		const body = html({
			rows: 40,
			total: 40,
			lines: ['Nothing further ahead.'],
			lineKey: '/items'
		});
		expect(body).toContain('Nothing further ahead.');
		expect(body).toContain('40 items in all.');
	});

	it('keeps a failed page plain, with no flavour line', () => {
		const body = html({ hasMore: true, failed: true, rows: 40, lines: ['Nothing further ahead.'] });
		expect(body).not.toContain('Nothing further ahead.');
	});
});
