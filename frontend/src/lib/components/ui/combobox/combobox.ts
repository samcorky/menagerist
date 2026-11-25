import { foldText } from '$lib/fold-text';

export type ComboboxItem = {
	value: string;
	/** Shown in the list. */
	label: string;
	/** Heading the item sits under; items without one come first, ungrouped. */
	group?: string;
	/** A name shown before the label with a muted chevron between, such as a type's parent. */
	crumb?: string;
	/** Shown on the trigger when selected, if different from `label`. */
	selectedLabel?: string;
	/** Muted text on the right of the row, such as a count. */
	description?: string;
	/** Other words a search should find it by, such as a full name the label shortens. */
	keywords?: string;
	disabled?: boolean;
};

export type ComboboxGroup = { heading: string | null; items: ComboboxItem[] };

/** Items whose label, group and keywords together contain every word of the query. */
export function filterComboboxItems(items: ComboboxItem[], query: string): ComboboxItem[] {
	const words = foldText(query).split(/\s+/).filter(Boolean);
	if (words.length === 0) return items;
	return items.filter((item) => {
		const haystack = foldText(
			`${item.group ?? ''} ${item.crumb ?? ''} ${item.label} ${item.keywords ?? ''}`
		);
		return words.every((word) => haystack.includes(word));
	});
}

/** Groups in first-seen order; ungrouped items form one group with a null heading. */
export function groupComboboxItems(items: ComboboxItem[]): ComboboxGroup[] {
	const groups = new Map<string | null, ComboboxItem[]>();
	for (const item of items) {
		const key = item.group ?? null;
		const list = groups.get(key);
		if (list) list.push(item);
		else groups.set(key, [item]);
	}
	return [...groups].map(([heading, list]) => ({ heading, items: list }));
}

/** The values with `value` added, or removed if it is already there (order kept). */
export function toggleComboboxValue(values: readonly string[], value: string): string[] {
	return values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
}

/**
 * One entry per chosen value, in the order chosen. A value with no item (it was deleted, say)
 * keeps an entry labelled by `unknownLabel` so it can still be removed.
 */
export function selectedComboboxItems(
	items: ComboboxItem[],
	values: readonly string[],
	unknownLabel: (value: string) => string = (value) => value
): ComboboxItem[] {
	return values.map(
		(value) => selectedComboboxItem(items, value) ?? { value, label: unknownLabel(value) }
	);
}

export function selectedComboboxItem(
	items: ComboboxItem[],
	value: string
): ComboboxItem | undefined {
	return items.find((item) => item.value === value);
}
