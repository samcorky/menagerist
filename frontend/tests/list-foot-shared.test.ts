import { describe, expect, it } from 'vitest';

// Design §19: a paging list's foot is the shared ListFoot. Pages must not carry their own
// copy of the observer, spinner and end state, which is how they came to say nothing at the
// end of a list (#588).
const sources = import.meta.glob<string>(['../src/routes/**/*.svelte', '../src/lib/**/*.svelte'], {
	query: '?raw',
	import: 'default',
	eager: true
});

/** The one place an IntersectionObserver may page a list. */
const LIST_FOOT = '../src/lib/components/list-foot.svelte';

describe('shared list foot', () => {
	it('finds the component sources', () => {
		expect(Object.keys(sources).length).toBeGreaterThan(50);
		expect(sources[LIST_FOOT]).toBeDefined();
	});

	it('pages a list from ListFoot alone', () => {
		const offenders = Object.entries(sources)
			.filter(([path]) => path !== LIST_FOOT)
			.filter(([, source]) => /new IntersectionObserver/.test(source))
			.filter(([, source]) => /hasMore|HasMore/.test(source))
			.map(([path]) => path);
		expect(offenders).toEqual([]);
	});

	it('loads the next page further ahead than the old 200px margin', () => {
		expect(sources[LIST_FOOT]).not.toContain("rootMargin: '200px'");
		expect(sources[LIST_FOOT]).toContain('loadAheadMargin');
	});

	it('announces the foot politely rather than moving focus', () => {
		expect(sources[LIST_FOOT]).toContain('aria-live="polite"');
		expect(sources[LIST_FOOT]).not.toContain('.focus()');
	});

	it('gives every paging list a noun to count with', () => {
		const users = Object.entries(sources).filter(([, source]) => source.includes('<ListFoot'));
		expect(users.length).toBeGreaterThan(3);
		for (const [path, source] of users) {
			expect(source, `${path} passes a noun`).toMatch(/noun="/);
		}
	});
});
