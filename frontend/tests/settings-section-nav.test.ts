// Server-renders SettingsSectionNav in both variants: links on a desktop, a select on a phone.
import { describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'svelte';
import { render } from 'svelte/server';
// The shared lucide stub exports null, which cannot render; the select draws a chevron.
vi.mock('@lucide/svelte/icons/chevron-down', async () => ({
	default: (await import('./mocks/noop.svelte')).default
}));

import SettingsSectionNav from '$lib/components/settings-section-nav.svelte';

const sections = [
	{ key: 'backup', label: 'Backups', count: 3, href: '/admin/settings?section=backup' },
	{ key: 'media', label: 'Media', count: 2, href: '/admin/settings?section=media' }
];

function html(props: Partial<ComponentProps<typeof SettingsSectionNav>> = {}): string {
	return render(SettingsSectionNav, {
		props: { sections, active: 'media', variant: 'list', ...props }
	}).body;
}

describe('SettingsSectionNav', () => {
	it('lists each section as a link with its count', () => {
		const out = html();
		expect(out).toContain('aria-label="Settings sections"');
		expect(out).toContain('href="/admin/settings?section=backup"');
		expect(out).toContain('>Backups</span>');
		expect(out).toContain('>3</span>');
	});

	it('marks only the active section as the current page', () => {
		const out = html();
		expect(out.match(/aria-current="page"/g)).toHaveLength(1);
		expect(out).toMatch(/href="\/admin\/settings\?section=media"[^>]*aria-current="page"/);
	});

	it('is a select with the active section chosen on a phone', () => {
		const out = html({ variant: 'select' });
		expect(out).toContain('<select');
		expect(out).toContain('aria-label="Settings section"');
		expect(out).toContain('Backups (3)');
		expect(out).not.toContain('<nav');
		expect(out).toMatch(/<option[^>]*value="media"[^>]*selected|value="media"[^>]*selected/);
	});
});
