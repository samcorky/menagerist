// Browser-only keyboard interactions are covered by the E2E suite.
import { describe, expect, it, vi } from 'vitest';
import { render } from 'svelte/server';

vi.mock('@lucide/svelte/icons/chevron-down', async () => ({
	default: (await import('./mocks/noop.svelte')).default
}));

import Combobox from '$lib/components/ui/combobox/combobox.svelte';
import {
	filterComboboxItems,
	groupComboboxItems,
	selectedComboboxItem,
	type ComboboxItem
} from '$lib/components/ui/combobox/combobox';

const ITEMS: ComboboxItem[] = [
	{ value: 'any', label: 'Name' },
	{ value: 'film:year', label: 'Year', group: 'Film', selectedLabel: 'Film › Year' },
	{ value: 'film:cafe', label: 'Café', group: 'Film', selectedLabel: 'Film › Café' },
	{ value: 'book:year', label: 'Year', group: 'Book', selectedLabel: 'Book › Year' },
	{ value: 'book:old', label: 'Old', group: 'Book', disabled: true }
];

describe('filterComboboxItems', () => {
	it('returns everything for a blank query', () => {
		expect(filterComboboxItems(ITEMS, '')).toEqual(ITEMS);
		expect(filterComboboxItems(ITEMS, '   ')).toEqual(ITEMS);
	});

	it('ignores case and accents in labels', () => {
		expect(filterComboboxItems(ITEMS, 'CAFE').map((i) => i.value)).toEqual(['film:cafe']);
		expect(filterComboboxItems(ITEMS, 'café').map((i) => i.value)).toEqual(['film:cafe']);
	});

	it('matches group names, so a group name lists its items', () => {
		expect(filterComboboxItems(ITEMS, 'book').map((i) => i.value)).toEqual([
			'book:year',
			'book:old'
		]);
	});

	it('needs every word to match the label or the group', () => {
		expect(filterComboboxItems(ITEMS, 'film year').map((i) => i.value)).toEqual(['film:year']);
		expect(filterComboboxItems(ITEMS, 'year zzz')).toEqual([]);
	});

	it('does not hide disabled items', () => {
		expect(filterComboboxItems(ITEMS, 'old')).toHaveLength(1);
	});
});

describe('groupComboboxItems', () => {
	it('puts ungrouped items first-in-place and keeps first-seen group order', () => {
		const groups = groupComboboxItems(ITEMS);
		expect(groups.map((g) => g.heading)).toEqual([null, 'Film', 'Book']);
		expect(groups[1].items.map((i) => i.value)).toEqual(['film:year', 'film:cafe']);
	});

	it('merges a group that reappears later', () => {
		const groups = groupComboboxItems([
			{ value: '1', label: 'a', group: 'X' },
			{ value: '2', label: 'b', group: 'Y' },
			{ value: '3', label: 'c', group: 'X' }
		]);
		expect(groups.map((g) => g.items.length)).toEqual([2, 1]);
	});

	it('is empty for no items', () => {
		expect(groupComboboxItems([])).toEqual([]);
	});
});

describe('selectedComboboxItem', () => {
	it('finds the item for a value, or nothing', () => {
		expect(selectedComboboxItem(ITEMS, 'book:year')?.group).toBe('Book');
		expect(selectedComboboxItem(ITEMS, 'blank')).toBeUndefined();
	});
});

describe('Combobox trigger', () => {
	const html = (props: Record<string, unknown>) =>
		render(Combobox, { props: { items: ITEMS, value: '', ...props } }).body;

	it('is a combobox button with the given accessible name', () => {
		const out = html({ 'aria-label': 'Condition 1, field', id: 'f1' });
		expect(out).toMatch(/<button[^>]*role="combobox"/);
		expect(out).toContain('aria-label="Condition 1, field"');
		expect(out).toContain('id="f1"');
		expect(out).toContain('aria-expanded="false"');
		expect(out).toContain('aria-haspopup="listbox"');
	});

	it('passes aria-labelledby through', () => {
		expect(html({ 'aria-labelledby': 'lbl' })).toContain('aria-labelledby="lbl"');
	});

	it('shows the placeholder when nothing matches the value', () => {
		expect(html({ placeholder: 'Choose what to filter on' })).toContain('Choose what to filter on');
	});

	it('shows the selected item, preferring its full label', () => {
		const out = html({ value: 'film:year' });
		expect(out).toContain('Film › Year');
	});

	it('falls back to the plain label', () => {
		expect(html({ value: 'any' })).toContain('Name');
	});

	it('can be disabled', () => {
		expect(html({ disabled: true })).toMatch(/<button[^>]*disabled/);
	});
});
