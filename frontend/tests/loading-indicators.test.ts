import { describe, expect, it } from 'vitest';

// Design §13a: known layouts use matching skeletons and never show a spinner beside them.
// Page-level loaders must not be hand-rolled spinners; a paging list's foot uses the shared
// ListFoot, and in-place actions use ui/spinner or an animated icon.
const sources = import.meta.glob<string>('../src/routes/**/*.svelte', {
	query: '?raw',
	import: 'default',
	eager: true
});

const handRolledSpinner =
	/animate-spin[^"'`]*rounded-full[^"'`]*border|rounded-full[^"'`]*border[^"'`]*animate-spin/;

describe('loading indicators', () => {
	it('finds the route sources', () => {
		expect(Object.keys(sources).length).toBeGreaterThan(20);
	});

	it('has no hand-rolled border spinners in routes', () => {
		const offenders = Object.entries(sources)
			.filter(([, source]) => handRolledSpinner.test(source))
			.map(([path]) => path);
		expect(offenders).toEqual([]);
	});
});
