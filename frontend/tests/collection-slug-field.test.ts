// Server-renders the slug field of the collection edit dialog.
import { describe, expect, it, vi } from 'vitest';
import { render } from 'svelte/server';

vi.mock('$lib/components/ui/label/index.js', async () => ({
	Label: (await import('./mocks/label.svelte')).default
}));

import CollectionSlugField from '$lib/components/collection-slug-field.svelte';

const html = (props: Record<string, unknown>) =>
	render(CollectionSlugField, { props: { ...base, ...props } }).body.replace(/\s+/g, ' ');
const buttonDisabled = (body: string) => /<button[^>]* disabled(?![:\w-])/.test(body);

const base = { value: 'my-films', onRegenerate: () => {} };

describe('CollectionSlugField', () => {
	it('shows the current slug under a Slug label with the link warning', () => {
		const body = html({});
		expect(body).toMatch(/<label for="edit-collection-slug">(<!---->)?Slug/);
		expect(body).toContain('value="my-films"');
		expect(body).toContain(
			"Changing the slug changes this collection's link. Links that use the old slug will stop working."
		);
		expect(body).toContain('Regenerate from name');
		expect(body).not.toContain('role="alert"');
	});

	it('shows an inline error and marks the field invalid', () => {
		const body = html({ error: 'That link is already used by another collection.' });
		expect(body).toContain('That link is already used by another collection.');
		expect(body).toContain('aria-invalid="true"');
		expect(body).toContain('edit-collection-slug-error');
	});

	it('disables regenerate while saving or when the name is unsaved', () => {
		const idle = html({});
		const unsaved = html({ nameUnsaved: true });
		const busy = html({ regenerating: true });
		expect(buttonDisabled(idle)).toBe(false);
		expect(buttonDisabled(unsaved)).toBe(true);
		expect(buttonDisabled(busy)).toBe(true);
		expect(unsaved).toContain('Save the new name first');
		expect(busy).toContain('Regenerating…');
	});
});
