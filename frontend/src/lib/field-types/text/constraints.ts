/**
 * Starts-with / ends-with constraints on a text field, stored as anchored JSON Schema patterns.
 *
 * Only literal text, escaped syntax characters, `^` and `$` are ever generated, so Python's `re`
 * and JavaScript's `u`-flag RegExp agree (see docs/field-types.md). The pattern is the single
 * source of truth: `parseConstraints` recovers the two inputs by reading exactly what
 * `constraintKeywords` writes, and treats anything else as a custom pattern to pass through.
 */

export type TextConstraints = { startsWith: string; endsWith: string };

/** Pattern keywords of a property that the editor did not write; re-emitted unchanged. */
export type CustomPattern = { pattern?: unknown; allOf?: unknown };

const SYNTAX = new Set('\\^$.*+?()[]{}|/');

/** Escape regex syntax characters. `-` is left alone: `\-` is invalid under the `u` flag. */
export function escapeLiteral(text: string): string {
	let out = '';
	for (const ch of text) out += SYNTAX.has(ch) ? '\\' + ch : ch;
	return out;
}

/** Inverse of `escapeLiteral`; null when `text` is not exactly what it would produce. */
export function unescapeLiteral(text: string): string | null {
	let out = '';
	const chars = [...text];
	for (let i = 0; i < chars.length; i++) {
		const ch = chars[i];
		if (ch === '\\') {
			const next = chars[++i];
			if (next === undefined || !SYNTAX.has(next)) return null;
			out += next;
		} else if (SYNTAX.has(ch)) {
			return null;
		} else {
			out += ch;
		}
	}
	return out;
}

type Half = { kind: 'start' | 'end'; literal: string };

function parseHalf(pattern: unknown): Half | null {
	if (typeof pattern !== 'string') return null;
	if (pattern.startsWith('^')) {
		const literal = unescapeLiteral(pattern.slice(1));
		if (literal) return { kind: 'start', literal };
	}
	if (pattern.endsWith('$')) {
		const literal = unescapeLiteral(pattern.slice(0, -1));
		if (literal) return { kind: 'end', literal };
	}
	return null;
}

/** Keywords to merge into a string property for the given constraints. */
export function constraintKeywords(c: Partial<TextConstraints>): {
	pattern?: string;
	allOf?: { pattern: string }[];
} {
	const patterns: string[] = [];
	if (c.startsWith) patterns.push('^' + escapeLiteral(c.startsWith));
	if (c.endsWith) patterns.push(escapeLiteral(c.endsWith) + '$');
	if (patterns.length === 0) return {};
	if (patterns.length === 1) return { pattern: patterns[0] };
	return { allOf: patterns.map((pattern) => ({ pattern })) };
}

/**
 * Read a property's constraints. `custom` is set (and `constraints` empty) when its `pattern` or
 * `allOf` is anything other than the forms `constraintKeywords` writes.
 */
export function parseConstraints(prop: { pattern?: unknown; allOf?: unknown }): {
	constraints: TextConstraints;
	custom: CustomPattern | null;
} {
	const constraints: TextConstraints = { startsWith: '', endsWith: '' };
	const hasPattern = prop.pattern !== undefined;
	const hasAllOf = prop.allOf !== undefined;
	if (!hasPattern && !hasAllOf) return { constraints, custom: null };

	const custom: CustomPattern = {};
	if (hasPattern) custom.pattern = prop.pattern;
	if (hasAllOf) custom.allOf = prop.allOf;

	let halves: (Half | null)[] | null = null;
	if (hasPattern && !hasAllOf) halves = [parseHalf(prop.pattern)];
	else if (hasAllOf && !hasPattern && Array.isArray(prop.allOf) && prop.allOf.length === 2) {
		halves = prop.allOf.map((item: unknown) => {
			const keys = typeof item === 'object' && item !== null ? Object.keys(item as object) : ['?'];
			return keys.length === 1 && keys[0] === 'pattern'
				? parseHalf((item as { pattern: unknown }).pattern)
				: null;
		});
		// The writer always emits the start half first; anything else is left as written.
		if (halves[0]?.kind !== 'start' || halves[1]?.kind !== 'end') halves = null;
	}
	if (!halves || halves.some((h) => h === null)) return { constraints, custom };
	for (const h of halves as Half[]) {
		if (h.kind === 'start') constraints.startsWith = h.literal;
		else constraints.endsWith = h.literal;
	}
	return { constraints, custom: null };
}

/** Friendly wording for a generated pattern, or null when it is not one of ours. */
export function describePattern(pattern: unknown): string | null {
	const half = parseHalf(pattern);
	if (!half) return null;
	return `Must ${half.kind === 'start' ? 'start' : 'end'} with "${half.literal}"`;
}

/** Helper text for a field's rule, for example: Must start with "cover-" and end with ".jpg". */
export function describeConstraints(c: Partial<TextConstraints>): string | null {
	const parts: string[] = [];
	if (c.startsWith) parts.push(`start with "${c.startsWith}"`);
	if (c.endsWith) parts.push(`end with "${c.endsWith}"`);
	return parts.length ? `Must ${parts.join(' and ')}` : null;
}

/** Editor state for a text field's constraints, kept in `EditorField.config`. */
export function readTextConfig(field: { config?: Record<string, unknown> }) {
	const c = field.config ?? {};
	return {
		startsWith: typeof c.startsWith === 'string' ? c.startsWith : '',
		endsWith: typeof c.endsWith === 'string' ? c.endsWith : '',
		custom: (c.custom ?? null) as Record<string, unknown> | null
	};
}
