export type UsageKind = 'node' | 'edge';

function noun(count: number, kind: UsageKind): string {
	const base = kind === 'node' ? 'item' : 'connection';
	return count === 1 ? base : `${base}s`;
}

/** "Used by 3 items" / "Used by 1 connection" / "Not used". */
export function usageLabel(count: number, kind: UsageKind): string {
	return count === 0 ? 'Not used' : `Used by ${count} ${noun(count, kind)}`;
}

/** Warning shown before a field's values are permanently deleted. */
export function purgeWarning(label: string, count: number, kind: UsageKind): string {
	return `This permanently deletes “${label}” from ${count} ${noun(count, kind)}. It cannot be undone.`;
}

/** Note shown after removing a choice option that stored values still use. */
export function optionRemovalWarning(option: string, count: number, kind: UsageKind): string {
	return `“${option}” is used by ${count} ${noun(count, kind)}. They keep it, shown as (no longer an option).`;
}
