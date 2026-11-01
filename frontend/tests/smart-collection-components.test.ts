// Server-renders the smart collection components to check what they show.
import { describe, expect, it, vi } from 'vitest';
import { render } from 'svelte/server';

vi.mock('@lucide/svelte', async () => {
	const Noop = (await import('./mocks/noop.svelte')).default;
	return { TriangleAlert: Noop, X: Noop };
});
vi.mock('$lib/components/ui/responsive-dialog/index.js', async () => {
	const Passthrough = (await import('./mocks/passthrough.svelte')).default;
	return { Root: Passthrough, Content: Passthrough, Description: Passthrough };
});

import SaveSmartCollectionDialog from '$lib/components/save-smart-collection-dialog.svelte';
import CollectionCount from '$lib/components/collection-count.svelte';
import SmartConditions from '$lib/components/smart-conditions.svelte';
import { UNREADABLE_CONDITIONS_MESSAGE } from '$lib/smart-collections';
import type { Query } from '$lib/query/types';

const lookup = { typeLabel: (s: string) => s, fieldLabel: (_t: string, k: string) => k };
const query: Query = {
	v: 1,
	where: { op: 'and', children: [{ kind: 'favourite', value: true }] },
	sort: []
};

describe('SmartConditions', () => {
	it('shows the conditions as read-only chips', () => {
		const { body } = render(SmartConditions, {
			props: { definition: query, lookup, warnings: [] }
		});
		expect(body).toContain('aria-label="Conditions"');
		expect(body).toContain('Is a favourite');
		expect(body).not.toContain('<button');
	});

	it('flags a condition the server could not match', () => {
		const { body } = render(SmartConditions, {
			props: {
				definition: query,
				lookup,
				warnings: [{ path: 'where.children[0]', message: 'gone' }]
			}
		});
		expect(body).toContain('border-destructive');
	});

	it('says so when the definition cannot be read', () => {
		const { body } = render(SmartConditions, {
			props: { definition: { v: 9 }, lookup, warnings: [] }
		});
		expect(body).toMatch(/These conditions can.{1,6}t be shown/);
		expect(UNREADABLE_CONDITIONS_MESSAGE).toContain('conditions');
		expect(body).not.toContain('<ul');
	});
});

describe('SaveSmartCollectionDialog', () => {
	it('asks for a name and offers a labelled save button', () => {
		const { body } = render(SaveSmartCollectionDialog, {
			props: { open: true, query, onsaved: () => {} }
		});
		expect(body).toContain('Save as smart collection');
		expect(body).toMatch(/<input[^>]*id="[^"]*-name"[^>]*required/);
		expect(body).toContain('Save smart collection');
		expect(body).toContain('Cancel');
	});
});

describe('CollectionCount', () => {
	const base = { id: 'c1', kind: 'dynamic', definition: query, item_count: 1000 } as const;

	it('shows the capped label with no button until a request fails', () => {
		const capped = render(CollectionCount, {
			props: { collection: { ...base, item_count_capped: true } }
		}).body;
		expect(capped).toContain('1,000+ items');
		expect(capped).not.toContain('Count exactly');
		expect(capped).toContain('aria-live="polite"');

		const exact = render(CollectionCount, {
			props: { collection: { ...base, item_count: 12, item_count_capped: false } }
		}).body;
		expect(exact).toContain('12 items');
		expect(exact).not.toContain('<button');
	});

	it('leaves a manual collection as it was', () => {
		const { body } = render(CollectionCount, {
			props: { collection: { id: 'm', kind: 'manual', item_count: 1, item_count_capped: false } }
		});
		expect(body).toContain('1 item');
		expect(body).not.toContain('<button');
	});
});
