import { describe, expect, it } from 'vitest';
import {
	CREATE_PREFIX,
	NONE_VALUE,
	buildTypeItems,
	createdLabel,
	groupTypeItems
} from '$lib/type-picker';

const type = (slug: string, label: string) => ({ id: slug, slug, label }) as never;
const types = [
	type('record', 'Record'),
	type('film', 'Film'),
	type('book', 'Book'),
	type('board-game', 'Board game')
];
const counts = new Map([
	['film', 9],
	['book', 4]
]);
const build = (query = '', over: Partial<Parameters<typeof buildTypeItems>[0]> = {}) =>
	buildTypeItems({ types, counts, query, allowClear: false, ...over });

describe('buildTypeItems', () => {
	it('offers no Create row when creating is not allowed', () => {
		const items = build('Nothing like it', { allowCreate: false });
		expect(items.some((item) => item.value.startsWith(CREATE_PREFIX))).toBe(false);
	});

	it('lists the types in use first, biggest first, with their counts', () => {
		const used = build().filter((item) => item.group === 'In use');
		expect(used.map((item) => item.value)).toEqual(['film', 'book']);
		expect(used.map((item) => item.description)).toEqual(['9', '4']);
	});

	it('lists the other types after them, by name', () => {
		const others = build().filter((item) => item.group === 'Other item types');
		expect(others.map((item) => item.value)).toEqual(['board-game', 'record']);
		expect(others.every((item) => item.description === undefined)).toBe(true);
	});

	it('has no In use heading when nothing is in use yet', () => {
		const items = build('', { counts: new Map() });
		expect(items.some((item) => item.group === 'In use')).toBe(false);
	});

	it('offers a way to choose no type when allowed, and only without a search', () => {
		expect(build('', { allowClear: true })[0]).toMatchObject({ value: NONE_VALUE });
		expect(build('', { allowClear: false }).some((i) => i.value === NONE_VALUE)).toBe(false);
		expect(build('fil', { allowClear: true }).some((i) => i.value === NONE_VALUE)).toBe(false);
	});

	it('filters by what was typed, in either the label or the slug', () => {
		expect(build('gam').map((item) => item.value)).toEqual(['board-game', `${CREATE_PREFIX}gam`]);
		expect(build('FILM').map((item) => item.value)).toContain('film');
	});

	it('offers to create a type when nothing has exactly that name', () => {
		const create = build('Vinyl').find((item) => item.value.startsWith(CREATE_PREFIX));
		expect(create).toMatchObject({ value: `${CREATE_PREFIX}Vinyl`, label: 'Create “Vinyl”' });
	});

	it('puts the create row last, under its own heading', () => {
		const items = build('fi');
		expect(items[items.length - 1]).toMatchObject({ group: 'New item type' });
	});

	it('does not offer to create a name that already exists, however it is written', () => {
		for (const query of ['Film', 'film', '  FILM  ', 'Board Game', 'board-game']) {
			expect(build(query).some((item) => item.value.startsWith(CREATE_PREFIX))).toBe(false);
		}
	});

	it('offers nothing to create for a blank search', () => {
		expect(build('   ').some((item) => item.value.startsWith(CREATE_PREFIX))).toBe(false);
	});

	it('trims what it offers to create', () => {
		expect(build('  Vinyl  ').find((i) => i.value.startsWith(CREATE_PREFIX))?.value).toBe(
			`${CREATE_PREFIX}Vinyl`
		);
	});
});

describe('buildTypeItems with subtypes', () => {
	const sub = (slug: string, label: string, parent: string) =>
		({ id: slug, slug, label, parent }) as never;
	const family = [
		type('memorabilia', 'Memorabilia'),
		sub('poster', 'Poster', 'memorabilia'),
		sub('figure', 'Action figure', 'memorabilia'),
		type('film', 'Film'),
		type('book', 'Book')
	];
	const make = (
		query = '',
		counts = new Map<string, number>(),
		over: Partial<Parameters<typeof buildTypeItems>[0]> = {}
	) => buildTypeItems({ types: family, counts, query, allowClear: false, ...over });
	const heading = (items: ReturnType<typeof make>, group: string) =>
		items.filter((i) => i.group === group).map((i) => i.value);

	it('groups the types of a family under their parent, the parent first', () => {
		expect(heading(make(), 'Memorabilia')).toEqual(['memorabilia', 'figure', 'poster']);
	});

	it('leaves types with no subtypes among the others', () => {
		expect(heading(make(), 'Other item types')).toEqual(['book', 'film']);
	});

	it('names the parent as the crumb, which the list hides under the heading that says it', () => {
		const poster = make().find((i) => i.value === 'poster');
		expect(poster).toMatchObject({ label: 'Poster', crumb: 'Memorabilia', group: 'Memorabilia' });
		// The parent itself has none.
		expect(make().find((i) => i.value === 'memorabilia')?.crumb).toBeUndefined();
	});

	it('lists a subtype in use under In use, shown with its parent', () => {
		const items = make('', new Map([['poster', 3]]));
		const poster = items.find((i) => i.value === 'poster');
		expect(poster).toMatchObject({ group: 'In use', description: '3', crumb: 'Memorabilia' });
		// It is not repeated under its parent, which still has the rest of its family.
		expect(heading(items, 'Memorabilia')).toEqual(['memorabilia', 'figure']);
	});

	it('lists a parent in use under In use, and its unused subtypes under its heading', () => {
		const items = make('', new Map([['memorabilia', 5]]));
		expect(heading(items, 'In use')).toEqual(['memorabilia']);
		expect(heading(items, 'Memorabilia')).toEqual(['figure', 'poster']);
	});

	it('has no heading for a family that is wholly in use', () => {
		const items = make(
			'',
			new Map([
				['memorabilia', 1],
				['poster', 1],
				['figure', 1]
			])
		);
		expect(items.some((i) => i.group === 'Memorabilia')).toBe(false);
	});

	it('finds the subtypes by their parents name', () => {
		const found = make('memorabilia').map((i) => i.value);
		expect(found).toEqual(expect.arrayContaining(['memorabilia', 'poster', 'figure']));
		expect(found).not.toContain('film');
	});

	it('does not offer to create a name a subtype already has', () => {
		expect(make('Poster').some((i) => i.value.startsWith(CREATE_PREFIX))).toBe(false);
	});

	it('never repeats a type', () => {
		const items = make('', new Map([['poster', 3]]));
		const values = items.map((i) => i.value);
		expect(new Set(values).size).toBe(values.length);
	});
});

describe('groupTypeItems', () => {
	const sub = (slug: string, label: string, parent: string) =>
		({ id: slug, slug, label, parent }) as never;
	const all = [
		type('memorabilia', 'Memorabilia'),
		sub('poster', 'Poster', 'memorabilia'),
		type('film', 'Film'),
		sub('vinyl', 'Vinyl', 'music'),
		type('music', 'Music media'),
		type('book', 'Book')
	];

	it('lists types with no family first and ungrouped, by name', () => {
		const items = groupTypeItems(all);
		expect(items.filter((i) => !i.group).map((i) => i.value)).toEqual(['book', 'film']);
		expect(items.slice(0, 2).map((i) => i.value)).toEqual(['book', 'film']);
	});

	it('groups each family under its parent, the parent first, families by name', () => {
		const items = groupTypeItems(all).filter((i) => i.group);
		expect(items.map((i) => [i.group, i.value])).toEqual([
			['Memorabilia', 'memorabilia'],
			['Memorabilia', 'poster'],
			['Music media', 'music'],
			['Music media', 'vinyl']
		]);
	});

	it('gives a subtype its parent as the crumb, and a parent none', () => {
		const items = groupTypeItems(all);
		expect(items.find((i) => i.value === 'poster')?.crumb).toBe('Memorabilia');
		expect(items.find((i) => i.value === 'memorabilia')?.crumb).toBeUndefined();
	});

	it('treats a subtype whose parent is missing as a plain type', () => {
		const items = groupTypeItems([sub('lost', 'Lost', 'gone')]);
		expect(items).toEqual([{ value: 'lost', label: 'Lost' }]);
	});
});

describe('createdLabel', () => {
	it('reads the label back out of a create row', () => {
		expect(createdLabel(`${CREATE_PREFIX}Vinyl records`)).toBe('Vinyl records');
	});

	it('is null for a real type or no type', () => {
		expect(createdLabel('film')).toBeNull();
		expect(createdLabel(NONE_VALUE)).toBeNull();
	});
});
