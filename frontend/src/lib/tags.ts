/** Trim, lowercase and de-duplicate tags, dropping blanks - mirrors the backend's normalisation. */
export function normaliseTags(tags: string[]): string[] {
	return [...new Set(tags.map((tag) => tag.trim().toLowerCase()).filter((tag) => tag !== ''))];
}
