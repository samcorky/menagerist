// Server-renders the narrowed-view bar and the locked conditions.
import { describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'svelte';
import { render } from 'svelte/server';

vi.mock('@lucide/svelte', async () => {
	const Noop = (await import('./mocks/noop.svelte')).default;
	return { TriangleAlert: Noop, Lock: Noop, X: Noop, BookmarkPlus: Noop };
});

import NarrowedBar from '$lib/components/narrowed-bar.svelte';
import SmartConditions from '$lib/components/smart-conditions.svelte';
import { SAVE_TOO_LARGE_MESSAGE } from '$lib/query/narrow';
import type { Query } from '$lib/query/types';

const bar = (props: Partial<ComponentProps<typeof NarrowedBar>> = {}) =>
	render(NarrowedBar, {
		props: {
			text: 'Narrowed by 2 filters: 3 of 12 items',
			blockReason: null,
			onsave: () => {},
			onupdate: () => {},
			onclear: () => {},
			...props
		}
	}).body;

const button = (html: string, name: string) =>
	(html.match(/<button[\s\S]*?<\/button>/g) ?? []).find((b) => b.includes(name)) ?? '';

describe('NarrowedBar', () => {
	it('says how the view is narrowed and offers the three actions', () => {
		const html = bar();
		expect(html).toContain('Narrowed by 2 filters: 3 of 12 items');
		expect(html).toContain('Save as new smart collection');
		expect(html).toContain('Update this collection');
		expect(html).toContain('Clear');
		expect(html).not.toContain('role="alert"');
	});

	it('leaves the actions enabled when the combination can be saved', () => {
		const html = bar();
		expect(button(html, 'Save as new smart collection')).not.toMatch(/\sdisabled(=|\s|>)/);
		expect(button(html, 'Update this collection')).not.toMatch(/\sdisabled(=|\s|>)/);
	});

	it('disables both save actions and says why when the combination is too large', () => {
		const html = bar({ blockReason: SAVE_TOO_LARGE_MESSAGE });
		expect(html).toContain(SAVE_TOO_LARGE_MESSAGE);
		expect(button(html, 'Save as new smart collection')).toMatch(/\sdisabled(=|\s|>)/);
		expect(button(html, 'Update this collection')).toMatch(/\sdisabled(=|\s|>)/);
		expect(button(html, 'Clear')).not.toMatch(/\sdisabled(=|\s|>)/);
		expect(html).toMatch(/aria-describedby="[^"]+"/);
	});

	it('shows progress while the collection is being updated', () => {
		const html = bar({ updating: true });
		expect(button(html, 'Update this collection')).toMatch(/\sdisabled(=|\s|>)/);
	});
});

describe('SmartConditions locked', () => {
	const lookup = { typeLabel: (s: string) => s, fieldLabel: (_t: string, k: string) => k };
	const query: Query = {
		v: 1,
		where: { op: 'and', children: [{ kind: 'favourite', value: true }] },
		sort: []
	};

	it('marks the chips as the collection’s own', () => {
		const { body } = render(SmartConditions, {
			props: { definition: query, lookup, warnings: [], locked: true }
		});
		expect(body).toContain('aria-label="Conditions"');
		expect(body).toContain('Saved conditions');
		expect(body).toContain('Is a favourite');
		expect(body).not.toContain('<button');
	});

	it('shows no caption when not locked', () => {
		const { body } = render(SmartConditions, {
			props: { definition: query, lookup, warnings: [] }
		});
		expect(body).not.toContain('Saved conditions');
	});
});
