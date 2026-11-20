/** The stored value when it is set but no longer one of the options, otherwise null. */
export function staleChoice(value: unknown, options: string[]): string | null {
	return typeof value === 'string' && value !== '' && !options.includes(value) ? value : null;
}

/** How an option reads: its declared label, or the stored value itself when it has none. */
export function optionLabel(labels: Record<string, string> | undefined, value: string): string {
	return labels?.[value] ?? value;
}
