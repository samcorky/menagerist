import { foldText } from '$lib/fold-text';

export type ComboboxItem = {
	value: string;
	/** Shown in the list. */
	label: string;
	/** Heading the item sits under; items without one come first, ungrouped. */
	group?: string;
	/** Shown on the trigger when selected, if different from `label`. */
	selectedLabel?: string;
	disabled?: boolean;
};

export type ComboboxGroup = { heading: string | null; items: ComboboxItem[] };

/** Items whose label and group together contain every word of the query. */
export function filterComboboxItems(items: ComboboxItem[], query: string): ComboboxItem[] {
	const words = foldText(query).split(/\s+/).filter(Boolean);
	if (words.length === 0) return items;
	return items.filter((item) => {
		const haystack = foldText(`${item.group ?? ''} ${item.label}`);
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

export function selectedComboboxItem(
	items: ComboboxItem[],
	value: string
): ComboboxItem | undefined {
	return items.find((item) => item.value === value);
}
