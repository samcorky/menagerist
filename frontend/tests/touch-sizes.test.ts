// Touch-sized (44px) controls are opt-in via `pointer-coarse:`; on a mouse the compact Rhea sizes apply.
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, relative } from 'node:path';

const SRC = fileURLToPath(new URL('../src', import.meta.url));
const TOUCH_SIZE = /^(?:.*:)?(?:h|min-h|min-w|size)-11!?$/;
const TOUCH_ONLY = /(?:^|:)(?:pointer-coarse|max-sm|max-md):/;

/** Files that may keep a bare touch size, with how many tokens and why. */
const ALLOWED: Record<string, { count: number; reason: string }> = {
	'routes/+layout.svelte': {
		count: 6,
		reason: 'bottom navigation, rendered on phones only (md:hidden)'
	}
};

function svelteFiles(dir: string): string[] {
	return readdirSync(dir, { recursive: true, encoding: 'utf8' })
		.filter((f) => f.endsWith('.svelte'))
		.map((f) => join(dir, f));
}

describe('touch sizes', () => {
	it('only applies 44px sizes on coarse pointers or phones', () => {
		const offenders: string[] = [];
		const bare: Record<string, number> = {};
		for (const file of svelteFiles(SRC)) {
			const rel = relative(SRC, file).replaceAll('\\', '/');
			readFileSync(file, 'utf8')
				.split('\n')
				.forEach((line, i) => {
					for (const token of line.split(/[\s'"`{}]+/)) {
						if (!TOUCH_SIZE.test(token) || TOUCH_ONLY.test(token)) continue;
						bare[rel] = (bare[rel] ?? 0) + 1;
						if (!ALLOWED[rel]) offenders.push(`${rel}:${i + 1} ${token}`);
					}
				});
		}
		expect(offenders).toEqual([]);
		for (const [file, { count }] of Object.entries(ALLOWED)) {
			expect(bare[file] ?? 0).toBeLessThanOrEqual(count);
		}
	});
});
