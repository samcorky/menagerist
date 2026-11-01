/** The stored value when it is set but no longer one of the options, otherwise null. */
export function staleChoice(value: unknown, options: string[]): string | null {
	return typeof value === 'string' && value !== '' && !options.includes(value) ? value : null;
}
