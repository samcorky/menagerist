// Server-renders IconButton: the label must stay the accessible name, and touch devices reveal it.
import { describe, expect, it, vi } from 'vitest';
import { createRawSnippet, type ComponentProps } from 'svelte';
import { render } from 'svelte/server';

vi.mock('$lib/components/ui/tooltip/index.js', async () => ({
	Root: (await import('./mocks/tooltip/root.svelte')).default,
	Trigger: (await import('./mocks/tooltip/trigger.svelte')).default,
	Content: (await import('./mocks/tooltip/content.svelte')).default
}));

import IconButton from '$lib/components/icon-button.svelte';

const icon = createRawSnippet(() => ({ render: () => '<svg data-testid="icon"></svg>' }));

function html(props: Partial<ComponentProps<typeof IconButton>> = {}): string {
	return render(IconButton, { props: { label: 'Items', children: icon, ...props } }).body;
}

describe('IconButton', () => {
	it('renders the label as screen-reader text that touch devices reveal', () => {
		expect(html()).toMatch(
			/<span class="[^"]*\bsr-only\b[^"]*pointer-coarse:not-sr-only[^"]*">Items<\/span>/
		);
	});

	it('renders the icon', () => {
		expect(html()).toContain('data-testid="icon"');
	});

	it('renders an anchor when href is given', () => {
		const out = html({ href: '/items' });
		expect(out).toContain('<a');
		expect(out).toContain('href="/items"');
	});

	it('renders a button without href', () => {
		const out = html();
		expect(out).toContain('<button');
		expect(out).not.toContain('<a ');
	});

	it('passes variant and class through', () => {
		const out = html({ variant: 'secondary', class: 'ml-2' });
		expect(out).toContain('bg-secondary');
		expect(out).toContain('ml-2');
	});

	it('lets touch devices widen the icon button to fit its label', () => {
		expect(html()).toContain('pointer-coarse:w-auto');
	});

	it('can keep the label hidden on touch for crowded bars, at the 44px size', () => {
		const out = html({ labelOnTouch: false });
		expect(out).not.toContain('pointer-coarse:not-sr-only');
		expect(out).not.toContain('pointer-coarse:w-auto');
		expect(out).toContain('pointer-coarse:size-11');
		expect(out).toContain('sr-only');
	});
});
