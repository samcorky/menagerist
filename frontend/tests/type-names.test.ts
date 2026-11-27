import { describe, expect, it } from 'vitest';
import { groupByFamily, inFamilyOrder, typeNames, withFamilies } from '$lib/type-names';

const names = typeNames([
	{ slug: 'memorabilia', label: 'Memorabilia', parent: null },
	{ slug: 'poster', label: 'Poster', parent: 'memorabilia' },
	{ slug: 'film', label: 'Film' },
	{ slug: 'lost', label: 'Lost', parent: 'gone' }
]);

describe('inFamilyOrder', () => {
	const t = (slug: string, parent?: string) => ({ slug, label: slug, parent });

	it('puts each subtype straight after its parent, keeping the order otherwise', () => {
		const ordered = inFamilyOrder([
			t('poster', 'memo'),
			t('film'),
			t('memo'),
			t('figure', 'memo'),
			t('book')
		]);
		expect(ordered.map((x) => x.slug)).toEqual(['film', 'memo', 'poster', 'figure', 'book']);
	});

	it('keeps a subtype whose parent is missing where it was', () => {
		const ordered = inFamilyOrder([t('lost', 'gone'), t('film')]);
		expect(ordered.map((x) => x.slug)).toEqual(['lost', 'film']);
	});

	it('does not change what it is given', () => {
		const given = [t('poster', 'memo'), t('memo')];
		inFamilyOrder(given);
		expect(given.map((x) => x.slug)).toEqual(['poster', 'memo']);
	});
});

describe('groupByFamily', () => {
	const types = [
		{ slug: 'film', label: 'Film' },
		{ slug: 'memo', label: 'Memorabilia' },
		{ slug: 'poster', label: 'Poster', parent: 'memo' },
		{ slug: 'figure', label: 'Figure', parent: 'memo' }
	];
	const rows = (slugs: string[]) => slugs.map((slug) => ({ slug }));

	it('leaves types with no family ungrouped and groups the rest under the parent`s name', () => {
		const groups = groupByFamily(rows(['film', 'poster', 'memo', 'figure']), types);
		expect(groups.map((g) => [g.heading, g.options.map((o) => o.slug)])).toEqual([
			[null, ['film']],
			['Memorabilia', ['memo', 'poster', 'figure']]
		]);
	});

	it('keeps the order given within a group, the parent first', () => {
		const groups = groupByFamily(rows(['figure', 'poster']), types);
		expect(groups.map((g) => [g.heading, g.options.map((o) => o.slug)])).toEqual([
			['Memorabilia', ['figure', 'poster']]
		]);
	});

	it('says which row is the parent itself', () => {
		const [, family] = groupByFamily(rows(['film', 'memo', 'poster']), types);
		expect(family.options.map((o) => o.isParent)).toEqual([true, false]);
	});

	it('has no empty ungrouped group', () => {
		expect(groupByFamily(rows(['poster']), types).map((g) => g.heading)).toEqual(['Memorabilia']);
	});

	it('treats a row whose type is unknown as ungrouped', () => {
		expect(groupByFamily(rows(['mystery']), types)).toEqual([
			{ heading: null, options: [{ slug: 'mystery', isParent: false }] }
		]);
	});
});

describe('typeNames', () => {
	it('shows a top-level type as it is', () => {
		expect(names.short('film')).toBe('Film');
		expect(names.path('film')).toBe('Film');
		expect(names.spoken('film')).toBe('Film');
		expect(names.parentOf('film')).toBeUndefined();
	});

	it('shows a subtype with its parent in full, and alone in short', () => {
		expect(names.path('poster')).toBe('Memorabilia › Poster');
		expect(names.short('poster')).toBe('Poster');
	});

	it('says a subtype`s parent for a screen reader', () => {
		expect(names.spoken('poster')).toBe('Poster, a subtype of Memorabilia');
	});

	it('gives the parent type a subtype names', () => {
		expect(names.parentOf('poster')).toMatchObject({ slug: 'memorabilia' });
	});

	it('treats a subtype whose parent has gone as a plain type', () => {
		expect(names.path('lost')).toBe('Lost');
		expect(names.parentOf('lost')).toBeUndefined();
	});

	it('shows a slug nothing has as it is', () => {
		expect(names.short('deleted')).toBe('deleted');
		expect(names.path('deleted')).toBe('deleted');
		expect(names.spoken('deleted')).toBe('deleted');
	});

	it('answers for no type', () => {
		expect(names.path(null)).toBe('');
		expect(names.short(undefined)).toBe('');
	});
});

describe('withFamilies', () => {
	const t = (slug: string, label: string, parent?: string) => ({ slug, label, parent });
	const all = [
		t('film', 'Film'),
		t('memorabilia', 'Memorabilia'),
		t('poster', 'Poster', 'memorabilia'),
		t('ticket-stub', 'Ticket stub', 'memorabilia'),
		t('music', 'Music media'),
		t('vinyl', 'Vinyl', 'music'),
		t('lost', 'Lost', 'gone')
	];
	const pick = (...slugs: string[]) => all.filter((x) => slugs.includes(x.slug));
	const slugs = (matches: ReturnType<typeof pick>) =>
		inFamilyOrder(withFamilies(matches, all)).map((x) => x.slug);

	it('shows a match that has no family as it is', () => {
		expect(slugs(pick('film'))).toEqual(['film']);
	});

	it('brings the subtypes of a parent that matched', () => {
		expect(slugs(pick('memorabilia'))).toEqual(['memorabilia', 'poster', 'ticket-stub']);
	});

	it('brings the parent of a subtype that matched, and only that subtype', () => {
		expect(slugs(pick('poster'))).toEqual(['memorabilia', 'poster']);
		expect(slugs(pick('vinyl'))).toEqual(['music', 'vinyl']);
	});

	it('lists a family once when both the parent and a subtype matched', () => {
		expect(slugs(pick('memorabilia', 'poster'))).toEqual(['memorabilia', 'poster', 'ticket-stub']);
	});

	it('finds the family on pages the list has not loaded, since it reads the complete set', () => {
		// The server's matches hold only the subtype; its parent and the other subtype are elsewhere.
		const shown = withFamilies(pick('ticket-stub'), all);
		expect(shown.map((x) => x.slug)).toEqual(['ticket-stub', 'memorabilia']);
	});

	it('keeps the matches first, in the order the server gave them', () => {
		const shown = withFamilies(pick('music', 'film'), all);
		expect(shown.map((x) => x.slug)).toEqual(['film', 'music', 'vinyl']);
	});

	it('leaves out a subtype whose parent is gone unless it matched itself', () => {
		expect(slugs(pick('lost'))).toEqual(['lost']);
	});

	it('shows the matches as they are while the complete set has not loaded', () => {
		expect(withFamilies(pick('poster'), []).map((x) => x.slug)).toEqual(['poster']);
	});

	it('shows nothing for no matches', () => {
		expect(withFamilies([], all)).toEqual([]);
	});
});
