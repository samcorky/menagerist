import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const ROUTES = fileURLToPath(new URL('../src/routes', import.meta.url));
const OPT_OUT = /export\s+const\s+prerender\s*=\s*false\b/;
const OPT_OUT_FILES = ['+page.ts', '+page.js', '+layout.ts', '+layout.js'];

/** Every directory under src/routes that holds a page. */
function pageDirs(dir: string): string[] {
	const found = readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
		entry.isDirectory() ? pageDirs(join(dir, entry.name)) : []
	);
	return existsSync(join(dir, '+page.svelte')) ? [dir, ...found] : found;
}

/** True when this directory, or one above it inside src/routes, switches prerendering off. */
function optsOut(dir: string): boolean {
	for (
		let current = dir;
		current.startsWith(ROUTES) && current !== dirname(ROUTES);
		current = dirname(current)
	) {
		if (current === ROUTES) return false;
		for (const name of OPT_OUT_FILES) {
			const file = join(current, name);
			if (existsSync(file) && OPT_OUT.test(readFileSync(file, 'utf8'))) return true;
		}
	}
	return false;
}

describe('dynamic routes are not prerendered', () => {
	// The root layout prerenders every route. A page whose path has a [param] cannot be
	// crawled, so the production build (not the dev server) fails unless it opts out.
	const dynamic = pageDirs(ROUTES)
		.map((dir) => relative(ROUTES, dir))
		.filter((path) => /\[[^\]]+\]/.test(path));

	it('finds the dynamic routes it is meant to guard', () => {
		expect(dynamic).toContain(join('items', '[id]'));
		expect(dynamic).toContain(join('collections', '[id]'));
	});

	it.each(dynamic)('%s sets prerender = false', (path) => {
		expect(optsOut(join(ROUTES, path))).toBe(true);
	});
});
