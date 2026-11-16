/**
 * Picks one of a page's own flavour lines, stable for the page within a session (#102).
 *
 * Each page declares its lines beside the markup they appear in. A line sits
 * above the existing explanation and call to action and never replaces them.
 * Use this only for first-use empty states with nothing to fix or search for:
 * errors and "no results" states stay plain (design §11). Lines follow the
 * collector-facing terms in design §24 and use British English.
 *
 * The choice hashes a per-session seed with the page's path, so revisiting a
 * page shows the same line while another session, or another page, may not.
 */

const SEED_KEY = 'menagerist.line-seed';

let fallbackSeed: string | null = null;

/**
 * A random value kept for the browser tab's session. The real session lives in
 * an HttpOnly cookie the page cannot read, so this stands in for it. Falls back
 * to a per-load value when storage is unavailable.
 */
export function sessionSeed(): string {
	try {
		const stored = sessionStorage.getItem(SEED_KEY);
		if (stored) return stored;
		const created = Math.random().toString(36).slice(2);
		sessionStorage.setItem(SEED_KEY, created);
		return created;
	} catch {
		fallbackSeed ??= Math.random().toString(36).slice(2);
		return fallbackSeed;
	}
}

/** FNV-1a: small, stable and evenly spread enough to choose between a handful of lines. */
export function hashString(text: string): number {
	let hash = 0x811c9dc5;
	for (let i = 0; i < text.length; i++) {
		hash ^= text.charCodeAt(i);
		hash = Math.imul(hash, 0x01000193);
	}
	return hash >>> 0;
}

/** The line for `key` (normally the page path) in this session. */
export function pickEmptyLine(
	lines: readonly string[],
	key: string,
	seed: string = sessionSeed()
): string {
	if (lines.length === 0) throw new Error('pickEmptyLine needs at least one line');
	return lines[hashString(`${seed}|${key}`) % lines.length];
}
