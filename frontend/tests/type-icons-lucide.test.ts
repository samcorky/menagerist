import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { TYPE_ICONS, TYPE_ICON_WORDS } from '$lib/type-icons';

// The icon names are stored on the server, so one that Lucide later removes or renames would
// quietly turn into the generic icon. A Lucide upgrade that does that fails here instead.
describe('type icons against the installed Lucide package', () => {
	const index = readFileSync(
		join(process.cwd(), 'node_modules/@lucide/svelte/dist/icons/index.js'),
		'utf8'
	);
	const available = new Set(
		[...index.matchAll(/from '\.\/([a-z0-9-]+)\.svelte'/g)].map((m) => m[1])
	);
	const names = Object.keys(TYPE_ICONS);

	it('can see the package', () => {
		expect(available.size).toBeGreaterThan(1000);
	});

	it('only lists icons the package has', () => {
		expect(names.filter((name) => !available.has(name))).toEqual([]);
	});

	it('has search words for exactly the listed icons', () => {
		expect(Object.keys(TYPE_ICON_WORDS).sort()).toEqual([...names].sort());
	});

	it('uses names the server accepts (lower-case words joined by dashes)', () => {
		const shape = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
		expect(names.filter((name) => !shape.test(name) || name.length > 64)).toEqual([]);
	});
});
