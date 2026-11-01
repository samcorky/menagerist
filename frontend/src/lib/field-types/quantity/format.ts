/** "{value} {unit}" text for a quantity's stored `{value, unit}` object, or an empty parts list. */
export function quantityText(raw: unknown): string {
	if (typeof raw !== 'object' || raw === null) return '';
	const { value, unit } = raw as { value?: unknown; unit?: unknown };
	// Read-mode callers (the item page's row-based rendering, a group's table cells) pass this
	// through `attributesToRows`, which stringifies every sub-value of an object-typed field -
	// so a numeric `value` may arrive as the string "180", not the number 180.
	const numeric =
		typeof value === 'number'
			? value
			: typeof value === 'string' && value !== ''
				? Number(value)
				: undefined;
	const parts = [
		numeric !== undefined && !isNaN(numeric) ? String(numeric) : undefined,
		typeof unit === 'string' && unit !== '' ? unit : undefined
	].filter((p): p is string => p !== undefined);
	return parts.join(' ');
}
