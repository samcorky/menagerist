// Server-renders SettingsTile: every settings entry shares one anchor with icon, title, description and chevron.
import { describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'svelte';
import { render } from 'svelte/server';
import Noop from './mocks/noop.svelte';

// The shared lucide stub exports null, which cannot render; the chevron needs a component.
vi.mock('@lucide/svelte', async () => ({
	ChevronRight: (await import('./mocks/noop.svelte')).default
}));

import SettingsTile from '$lib/components/settings-tile.svelte';

function html(props: Partial<ComponentProps<typeof SettingsTile>> = {}): string {
	return render(SettingsTile, {
		props: {
			href: '/settings/account',
			icon: Noop as unknown as ComponentProps<typeof SettingsTile>['icon'],
			title: 'Account',
			description: 'Change your password.',
			...props
		}
	}).body;
}

describe('SettingsTile', () => {
	it('is a single link to the destination', () => {
		const out = html();
		expect(out).toMatch(/^<!--[^>]*--><a /);
		expect(out).toContain('href="/settings/account"');
		expect(out.match(/<a /g)).toHaveLength(1);
	});

	it('shows the title and one-line description', () => {
		const out = html();
		expect(out).toContain('>Account</p>');
		expect(out).toContain('>Change your password.</p>');
	});

	it('wraps long text instead of overflowing', () => {
		const out = html({ title: 'T'.repeat(200), description: 'd'.repeat(200) });
		expect(out.match(/overflow-wrap:anywhere/g)).toHaveLength(2);
		expect(out).toContain('min-w-0');
	});

	it('shows a visible keyboard focus ring and a hover state', () => {
		const out = html();
		expect(out).toContain('focus-visible:ring-[3px]');
		expect(out).toContain('hover:bg-muted/50');
	});

	it('keeps a touch-friendly minimum height', () => {
		expect(html()).toContain('min-h-20');
	});
});
