export type UsageKind = 'node' | 'edge';

function noun(count: number, kind: UsageKind): string {
	const base = kind === 'node' ? 'item' : 'connection';
	return count === 1 ? base : `${base}s`;
}

/** "Used by 3 items" / "Used by 1 connection" / "Not used". */
export function usageLabel(count: number, kind: UsageKind): string {
	return count === 0 ? 'Not used' : `Used by ${count} ${noun(count, kind)}`;
}

/**
 * Warning shown before a field's values are permanently deleted. The count is
 * the viewer's own; the purge also reaches other people's content.
 */
export function purgeWarning(label: string, count: number, kind: UsageKind): string {
	const many = noun(2, kind);
	return `This permanently deletes “${label}” from ${count} of your ${many}, and from any other person's ${many} that use it. It cannot be undone.`;
}

/** Note shown after removing a choice option that stored values still use. */
export function optionRemovalWarning(option: string, count: number, kind: UsageKind): string {
	return `“${option}” is used by ${count} ${noun(count, kind)}. They keep it, shown as (no longer an option).`;
}
