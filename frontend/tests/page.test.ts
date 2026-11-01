// Server-renders Page: the width classes per page type and the shell's alignment override.
import { describe, expect, it } from 'vitest';
import { createRawSnippet, type ComponentProps } from 'svelte';
import { render } from 'svelte/server';

import Page from '$lib/components/page.svelte';
import { PAGE_ALIGN } from '$lib/page-context';

const body = createRawSnippet(() => ({ render: () => '<p>content</p>' }));

function html(
	props: Partial<ComponentProps<typeof Page>> = {},
	align?: 'start' | 'center'
): string {
	const context = align ? new Map([[PAGE_ALIGN, { current: align }]]) : undefined;
	return render(Page, { props: { children: body, ...props }, context }).body;
}

describe('Page', () => {
	it('wraps its content in a main landmark', () => {
		expect(html()).toMatch(/<main[^>]*>[\s\S]*<p>content<\/p>/);
	});

	it('caps fluid pages at 2200px', () => {
		expect(html({ width: 'fluid' })).toContain('max-w-[2200px]');
	});

	it('uses max-w-5xl for reading pages, the default', () => {
		expect(html()).toContain('max-w-5xl');
		expect(html({ width: 'reading' })).toContain('max-w-5xl');
	});

	it('uses max-w-3xl for form pages', () => {
		expect(html({ width: 'form' })).toContain('max-w-3xl');
	});

	it('uses max-w-sm for narrow pages', () => {
		expect(html({ width: 'narrow' })).toContain('max-w-sm');
	});

	it('centres by default', () => {
		expect(html()).toContain('mx-auto');
	});

	it('keeps the auto margins when a parent asks for centring explicitly', () => {
		expect(html({}, 'center')).toContain('mx-auto');
	});

	it('drops the auto margins when a shell asks for start alignment', () => {
		expect(html({}, 'start')).not.toContain('mx-auto');
	});

	it('passes extra classes to the content column', () => {
		expect(html({ class: 'gap-8' })).toContain('gap-8');
	});
});
