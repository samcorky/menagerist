import { describe, expect, it } from 'vitest';
import { groupByFamily, inFamilyOrder, matchTypes, typeNames } from '$lib/type-names';

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

describe('matchTypes', () => {
	const t = (slug: string, label: string, parent?: string) => ({ slug, label, parent });
	const types = [
		t('film', 'Film'),
		t('memorabilia', 'Memorabilia'),
		t('poster', 'Poster', 'memorabilia'),
		t('ticket-stub', 'Ticket stub', 'memorabilia'),
		t('music', 'Music media'),
		t('vinyl', 'Vinyl', 'music'),
		t('lost', 'Lost', 'gone')
	];
	const slugs = (query: string) => matchTypes(types, query).map((x) => x.slug);

	it('keeps every type for a blank search', () => {
		expect(slugs('')).toEqual(types.map((x) => x.slug));
		expect(slugs('   ')).toEqual(types.map((x) => x.slug));
	});

	it('finds a type by its label or its slug, ignoring case', () => {
		expect(slugs('FILM')).toEqual(['film']);
		expect(slugs('ticket-stub')).toEqual(['memorabilia', 'ticket-stub']);
	});

	it('brings the subtypes of a parent that matches', () => {
		expect(slugs('memorabilia')).toEqual(['memorabilia', 'poster', 'ticket-stub']);
	});

	it('brings the parent of a subtype that matches, and only that subtype', () => {
		expect(slugs('poster')).toEqual(['memorabilia', 'poster']);
		expect(slugs('vinyl')).toEqual(['music', 'vinyl']);
	});

	it('lists a family once when both parent and subtype match', () => {
		// "o" is in Memorabilia and in Poster, and in Lost, which has no family.
		expect(slugs('o')).toEqual(['memorabilia', 'poster', 'ticket-stub', 'lost']);
	});

	it('keeps the order it was given', () => {
		expect(matchTypes([...types].reverse(), 'memorabilia').map((x) => x.slug)).toEqual([
			'ticket-stub',
			'poster',
			'memorabilia'
		]);
	});

	it('leaves out a subtype whose parent is gone unless it matches itself', () => {
		expect(slugs('lost')).toEqual(['lost']);
		expect(slugs('gone')).toEqual([]);
	});

	it('finds nothing for a search nothing matches', () => {
		expect(slugs('zzz')).toEqual([]);
	});
});
