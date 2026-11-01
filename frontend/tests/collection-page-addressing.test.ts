import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// The ETag cache is keyed by path, so after the page has loaded every call must use the id.
const source = readFileSync('src/routes/collections/[id]/+page.svelte', 'utf8');

describe('collection page addressing', () => {
	it('never addresses a collection call by the address segment', () => {
		const uses = [...source.matchAll(/collection_id:\s*([\w.?]+)/g)].map((m) => m[1]);
		expect(uses.length).toBeGreaterThan(4);
		for (const use of uses) {
			expect(['id', 'collection.id', 'canonicalId']).toContain(use);
		}
	});

	it('only passes the address segment to the first load', () => {
		const loads = [...source.matchAll(/(?<!function )loadCollection\(([^)]*)\)/g)].map((m) => m[1]);
		for (const load of loads) {
			if (load.startsWith('collectionId')) continue;
			expect(load).toMatch(/^(id|canonicalId|result\.data\.id)(, true)?$/);
		}
	});
});
