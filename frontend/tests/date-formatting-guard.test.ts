import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

// Dates and times are written only by `src/lib/format-date.ts`, which applies the person's time
// zone, date order and clock. Anything else writing a date directly would ignore them.
const SRC = join(__dirname, '..', 'src');
const DIRECT =
	/toLocaleDateString|toLocaleTimeString|Intl\.DateTimeFormat|toLocaleString\(\s*undefined\s*,\s*\{/;

// Each with the reason it may format a date itself.
const ALLOWED: Record<string, string> = {
	'lib/format-date.ts': 'the formatter',
	'lib/schedule-preview.ts': "cron runs, deliberately in the server's zone, which it names"
};

function sources(dir: string): string[] {
	return readdirSync(dir).flatMap((name) => {
		const path = join(dir, name);
		if (name === 'generated') return [];
		if (statSync(path).isDirectory()) return sources(path);
		return /\.(ts|svelte)$/.test(name) ? [path] : [];
	});
}

describe('date formatting', () => {
	it('happens only in the formatter', () => {
		const offenders = sources(SRC)
			.map((path) => relative(SRC, path).replaceAll('\\', '/'))
			.filter((path) => !(path in ALLOWED))
			.filter((path) => DIRECT.test(readFileSync(join(SRC, path), 'utf-8')));
		expect(offenders).toEqual([]);
	});

	it('allows only files that still exist', () => {
		const known = new Set(sources(SRC).map((p) => relative(SRC, p).replaceAll('\\', '/')));
		expect(Object.keys(ALLOWED).filter((path) => !known.has(path))).toEqual([]);
	});
});
