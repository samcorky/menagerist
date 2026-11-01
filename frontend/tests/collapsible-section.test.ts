// Server-renders CollapsibleSection: heading, count, the remembered open state and the actions slot.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createRawSnippet, type ComponentProps } from 'svelte';
import { render } from 'svelte/server';

vi.mock('@lucide/svelte', async () => ({
	ChevronDown: (await import('./mocks/noop.svelte')).default
}));
vi.mock('$lib/components/ui/collapsible/index.js', async () => ({
	Root: (await import('./mocks/collapsible/root.svelte')).default,
	Trigger: (await import('./mocks/collapsible/trigger.svelte')).default,
	Content: (await import('./mocks/collapsible/content.svelte')).default
}));

import CollapsibleSection from '$lib/components/collapsible-section.svelte';

const body = createRawSnippet(() => ({ render: () => '<p>inside</p>' }));
const actions = createRawSnippet(() => ({ render: () => '<span>act</span>' }));

function html(props: Partial<ComponentProps<typeof CollapsibleSection>> = {}): string {
	return render(CollapsibleSection, {
		props: { id: 'demo', title: 'Demo', children: body, ...props }
	}).body;
}

afterEach(() => vi.unstubAllGlobals());

describe('CollapsibleSection', () => {
	it('renders the title as a heading and the count', () => {
		const out = html({ count: 3 });
		expect(out).toMatch(
			/<h2[^>]*>(?:\s|<!--[^>]*-->)*<button[^>]*>.*Demo.*<\/button>(?:\s|<!--[^>]*-->)*<\/h2>/s
		);
		expect(out).toContain('>3<');
	});

	it('keeps the heading outside the button, never inside it', () => {
		expect(html()).not.toMatch(/<button[^>]*>(?:(?!<\/button>).)*<h[23]/s);
	});

	it('is open by default and exposes that to assistive technology', () => {
		expect(html()).toContain('aria-expanded="true"');
		expect(html()).toContain('inside');
	});

	it('starts closed when defaultOpen is false', () => {
		expect(html({ defaultOpen: false })).toContain('aria-expanded="false"');
	});

	it('uses the remembered state over the default', () => {
		vi.stubGlobal('localStorage', {
			getItem: (key: string) => (key === 'menagerist:section:demo' ? '0' : null),
			setItem: () => {}
		});
		expect(html()).toContain('aria-expanded="false"');
	});

	it('opens a remembered-closed section when it holds the current page', () => {
		vi.stubGlobal('localStorage', { getItem: () => '0', setItem: () => {} });
		expect(html({ forceOpen: true })).toContain('aria-expanded="true"');
	});

	it('renders the actions beside the heading', () => {
		expect(html({ actions })).toContain('<span>act</span>');
	});

	it('renders a lighter label when the heading is a paragraph', () => {
		expect(html({ heading: 'p' })).toMatch(
			/<p[^>]*>(?:\s|<!--[^>]*-->)*<button[^>]*>.*Demo.*<\/button>(?:\s|<!--[^>]*-->)*<\/p>/s
		);
	});
});
