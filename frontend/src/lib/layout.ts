export type LayoutFieldItem = { key: string };

export type LayoutSectionItem = {
	id: string;
	section: string;
	collapsed?: boolean;
	items: LayoutFieldItem[];
};

export type LayoutItem = LayoutFieldItem | LayoutSectionItem;

export type XLayout = LayoutItem[];

export function isSectionItem(item: LayoutItem): item is LayoutSectionItem {
	return 'section' in item;
}

/**
 * Produce a stable, renderable layout from a raw layout and the schema's properties.
 *
 * - No layout → flat list in schema key order (JSONB-sorted, but consistent)
 * - Dangling keys (properties removed since layout was saved) are silently dropped
 * - Unplaced keys (properties added since layout was saved) are appended at the end
 */
export function normalise(
	layout: XLayout | undefined,
	properties: Record<string, unknown>
): XLayout {
	const allKeys = Object.keys(properties);
	if (!layout || layout.length === 0) {
		return allKeys.map((key) => ({ key }));
	}

	const placed = new Set<string>();
	const result: XLayout = [];

	for (const item of layout) {
		if (isSectionItem(item)) {
			const validItems = item.items.filter((i) => allKeys.includes(i.key) && !placed.has(i.key));
			validItems.forEach((i) => placed.add(i.key));
			if (validItems.length > 0) result.push({ ...item, items: validItems });
		} else {
			if (allKeys.includes(item.key) && !placed.has(item.key)) {
				placed.add(item.key);
				result.push(item);
			}
		}
	}

	for (const key of allKeys) {
		if (!placed.has(key)) result.push({ key });
	}

	return result;
}

/** Extract ordered field keys from a layout, flattening sections. */
export function orderedKeys(layout: XLayout): string[] {
	return layout.flatMap((item) =>
		isSectionItem(item) ? item.items.map((i) => i.key) : [item.key]
	);
}
