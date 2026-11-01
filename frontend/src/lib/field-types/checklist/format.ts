/** How many of a checklist's rows are ticked, or `null` for an empty/non-array value. */
export function checklistCount(raw: unknown): { checked: number; total: number } | null {
	if (!Array.isArray(raw) || raw.length === 0) return null;
	const checked = raw.filter(
		(item) =>
			typeof item === 'object' && item !== null && (item as { done?: unknown }).done === true
	).length;
	return { checked, total: raw.length };
}
