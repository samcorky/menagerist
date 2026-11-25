// Browser-only keyboard interactions are covered by the E2E suite.
import { describe, expect, it, vi } from 'vitest';
import { render } from 'svelte/server';

vi.mock('@lucide/svelte/icons/chevron-down', async () => ({
	default: (await import('./mocks/noop.svelte')).default
}));
vi.mock('@lucide/svelte/icons/x', async () => ({
	default: (await import('./mocks/noop.svelte')).default
}));

import MultiCombobox from '$lib/components/ui/combobox/multi-combobox.svelte';
import {
	selectedComboboxItems,
	toggleComboboxValue,
	type ComboboxItem
} from '$lib/components/ui/combobox/combobox';

const ITEMS: ComboboxItem[] = [
	{ value: 'book', label: 'Book' },
	{ value: 'comic', label: 'Comic' },
	{ value: 'person', label: 'Person' }
];

describe('toggleComboboxValue', () => {
	it('adds a value that is not there, at the end', () => {
		expect(toggleComboboxValue(['book'], 'comic')).toEqual(['book', 'comic']);
	});

	it('removes a value that is there, keeping the order of the rest', () => {
		expect(toggleComboboxValue(['book', 'comic', 'person'], 'comic')).toEqual(['book', 'person']);
	});

	it('does not change the list it was given', () => {
		const values = ['book'];
		toggleComboboxValue(values, 'comic');
		expect(values).toEqual(['book']);
	});
});

describe('selectedComboboxItems', () => {
	it('lists the chosen items in the order chosen', () => {
		expect(selectedComboboxItems(ITEMS, ['person', 'book']).map((i) => i.label)).toEqual([
			'Person',
			'Book'
		]);
	});

	it('keeps a value with no item, labelled so it can be removed', () => {
		const out = selectedComboboxItems(ITEMS, ['gone'], (v) => `${v} (deleted)`);
		expect(out).toEqual([{ value: 'gone', label: 'gone (deleted)' }]);
	});

	it('labels an unknown value as itself by default', () => {
		expect(selectedComboboxItems(ITEMS, ['gone'])[0].label).toBe('gone');
	});

	it('is empty with nothing chosen', () => {
		expect(selectedComboboxItems(ITEMS, [])).toEqual([]);
	});
});

describe('MultiCombobox', () => {
	const html = (props: Record<string, unknown>) =>
		render(MultiCombobox, { props: { items: ITEMS, value: [], ...props } }).body;

	it('is a combobox button with the given accessible name', () => {
		const out = html({ 'aria-label': 'Starts from', id: 'f1' });
		expect(out).toMatch(/<button[^>]*role="combobox"/);
		expect(out).toContain('aria-label="Starts from"');
		expect(out).toContain('id="f1"');
		expect(out).toContain('aria-expanded="false"');
	});

	it('shows the placeholder and no chips with nothing chosen', () => {
		const out = html({ placeholder: 'Add an item type…' });
		expect(out).toContain('Add an item type…');
		expect(out).not.toContain('multi-combobox-chips');
	});

	it('shows a chip with a remove button for each chosen value', () => {
		const out = html({ value: ['book', 'person'] });
		expect(out).toContain('multi-combobox-chips');
		expect(out).toContain('aria-label="Remove Book"');
		expect(out).toContain('aria-label="Remove Person"');
		expect(out).not.toContain('Remove Comic');
	});

	it('keeps a chip for a value that has no item', () => {
		const out = html({ value: ['gone'], unknownLabel: (v: string) => `${v} (no longer there)` });
		expect(out).toContain('gone (no longer there)');
		expect(out).toContain('aria-label="Remove gone (no longer there)"');
	});

	it('names the remove buttons as asked', () => {
		const out = html({ value: ['book'], removeLabel: (l: string) => `Drop ${l}` });
		expect(out).toContain('aria-label="Drop Book"');
	});

	it('can be disabled, chips included', () => {
		const out = html({ value: ['book'], disabled: true });
		expect(out.match(/<button[^>]*disabled/g)).toHaveLength(2);
	});
});
