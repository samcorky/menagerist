/** "{value} {unit}" text for a quantity's stored `{value, unit}` object, or an empty parts list. */
export function quantityText(raw: unknown): string {
	if (typeof raw !== 'object' || raw === null) return '';
	const { value, unit } = raw as { value?: unknown; unit?: unknown };
	const parts = [
		typeof value === 'number' ? String(value) : undefined,
		typeof unit === 'string' && unit !== '' ? unit : undefined
	].filter((p): p is string => p !== undefined);
	return parts.join(' ');
}
