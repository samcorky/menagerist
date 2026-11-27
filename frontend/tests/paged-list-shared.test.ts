import { describe, expect, it } from 'vitest';

// A list that loads a page at a time uses `PagedList` (README, "Paged lists"), not its own
// `fetchPage`. Each page used to carry a copy that read the next page from the `Link` header
// with a regex, or asked for it with the last row's id, which only works in the default order.
const sources = import.meta.glob(
	['../src/routes/**/*.svelte', '../src/lib/**/*.svelte', '../src/lib/**/*.ts'],
	{ query: '?raw', import: 'default', eager: true }
) as Record<string, string>;

/** The one place the Link header is read. */
const PAGING = '../src/lib/paging.ts';

/**
 * Pages that keep their own paging state instead of a `PagedList`, until they move onto it
 * with their sort controls (#592, #610). They read the server's cursor with `nextCursor`, as
 * everything else does. Take a path off this list when it moves; never add one.
 */
const BY_HAND = new Set([
	'../src/routes/collections/[id]/+page.svelte',
	'../src/lib/query/items-page.ts',
	'../src/routes/items/+page.svelte'
]);

/** Pages a cursor by the id of the last row on purpose: an item's contents come in (depth, id) order. */
const POSITIONAL = new Set(['../src/lib/components/item-contents.svelte']);

const offenders = (pattern: RegExp, allowed: ReadonlySet<string>) =>
	Object.entries(sources)
		.filter(([path]) => path !== PAGING && !allowed.has(path))
		.filter(([, source]) => pattern.test(source))
		.map(([path]) => path)
		.sort();

describe('paged lists', () => {
	it('finds the sources', () => {
		expect(Object.keys(sources).length).toBeGreaterThan(100);
		expect(sources[PAGING]).toBeDefined();
		for (const path of [...BY_HAND, ...POSITIONAL]) expect(sources[path]).toBeDefined();
	});

	it('reads the next page from the Link header in one place', () => {
		expect(offenders(/rel="next"/, new Set())).toEqual([]);
	});

	it("asks for the next page with the server's cursor, not the last row's id", () => {
		expect(offenders(/\.at\(-1\)\?\.id/, POSITIONAL)).toEqual([]);
	});

	it('does not keep a list on the page-by-hand list once it has moved', () => {
		for (const path of BY_HAND) {
			expect(sources[path]).toMatch(/nextCursor|PagedList|cursor/);
		}
		expect(Object.entries(sources).filter(([, s]) => /new PagedList/.test(s))).not.toHaveLength(0);
	});
});
