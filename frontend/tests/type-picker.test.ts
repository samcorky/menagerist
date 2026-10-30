import { describe, expect, it } from 'vitest';
import { CREATE_PREFIX, NONE_VALUE, buildTypeItems, createdLabel } from '$lib/type-picker';

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

describe('createdLabel', () => {
	it('reads the label back out of a create row', () => {
		expect(createdLabel(`${CREATE_PREFIX}Vinyl records`)).toBe('Vinyl records');
	});

	it('is null for a real type or no type', () => {
		expect(createdLabel('film')).toBeNull();
		expect(createdLabel(NONE_VALUE)).toBeNull();
	});
});
