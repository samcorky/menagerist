// Server-renders TypeIcon: the type's colour classes, a boxed variant, and the generic fallback.
import { describe, expect, it, vi } from 'vitest';
import { render } from 'svelte/server';

vi.mock('@lucide/svelte', async () => ({ Package: (await import('./mocks/noop.svelte')).default }));
vi.mock('$lib/type-icons', async () => {
	const Noop = (await import('./mocks/noop.svelte')).default;
	return { TYPE_ICONS: { film: Noop }, TYPE_ICON_WORDS: { film: 'movie' } };
});

import TypeIcon from '$lib/components/type-icon.svelte';

const html = (props: Record<string, unknown>) => render(TypeIcon, { props }).body;

describe('TypeIcon', () => {
	it('uses the type colour for the icon', () => {
		const out = html({ icon: 'film', colour: 'red' });
		expect(out).toContain('text-red-600');
		expect(out).toContain('dark:text-red-400');
	});

	it('is neutral grey with no colour and still renders with no icon', () => {
		const out = html({ icon: null, colour: null });
		expect(out).toContain('text-neutral-600');
	});

	it('adds a tinted background when boxed', () => {
		const out = html({ icon: 'film', colour: 'blue', boxed: true });
		expect(out).toContain('bg-blue-500/10');
		expect(html({ icon: 'film', colour: 'blue' })).not.toContain('bg-blue-500/10');
	});

	it('passes extra classes through and hides itself from assistive technology', () => {
		const out = html({ icon: 'film', class: 'size-8' });
		expect(out).toContain('size-8');
		expect(out).toContain('aria-hidden="true"');
	});
});
