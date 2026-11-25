import { describe, expect, it } from 'vitest';
import {
	appearanceOf,
	inheritedFieldRows,
	inheritedFromParent,
	inheritedKeys,
	parentChoices
} from '$lib/type-inheritance';

const memorabilia = { slug: 'memorabilia', label: 'Memorabilia', icon: 'trophy', colour: 'amber' };
const types = [
	memorabilia,
	{ slug: 'poster', label: 'Poster', parent: 'memorabilia', icon: null, colour: null },
	{ slug: 'figure', label: 'Figure', parent: 'memorabilia', icon: 'drama', colour: null },
	{ slug: 'film', label: 'Film', icon: 'clapperboard', colour: 'red' }
];

describe('appearanceOf', () => {
	it('gives a type its own icon and colour', () => {
		expect(appearanceOf('film', types)).toEqual({ icon: 'clapperboard', colour: 'red' });
	});

	it('gives a subtype its parent`s until it sets its own', () => {
		expect(appearanceOf('poster', types)).toEqual({ icon: 'trophy', colour: 'amber' });
	});

	it('lets a subtype set one of them and keep the other from its parent', () => {
		expect(appearanceOf('figure', types)).toEqual({ icon: 'drama', colour: 'amber' });
	});

	it('is empty for no type, an unknown type, or a type with nothing set', () => {
		expect(appearanceOf(null, types)).toEqual({ icon: null, colour: null });
		expect(appearanceOf('gone', types)).toEqual({ icon: null, colour: null });
		expect(appearanceOf('x', [{ slug: 'x' }])).toEqual({ icon: null, colour: null });
	});

	it('ignores a parent that no longer exists', () => {
		const lost = [{ slug: 'lost', label: 'Lost', parent: 'gone', icon: null, colour: null }];
		expect(appearanceOf('lost', lost)).toEqual({ icon: null, colour: null });
	});
});

describe('parentChoices', () => {
	const t = (slug: string, parent?: string) => ({ slug, label: slug.toUpperCase(), parent });
	const all = [t('memo'), t('poster', 'memo'), t('film'), t('book')];

	it('offers the top-level types, in the order given', () => {
		expect(parentChoices(all, null).options.map((o) => o.slug)).toEqual(['memo', 'film', 'book']);
	});

	it('leaves out the type being edited, and is not locked', () => {
		const choices = parentChoices(all, t('film'));
		expect(choices.options.map((o) => o.slug)).toEqual(['memo', 'book']);
		expect(choices.lockedBy).toEqual([]);
	});

	it('is locked, naming the subtypes, when the type being edited is a parent', () => {
		const choices = parentChoices([...all, t('figure', 'memo')], t('memo'));
		expect(choices.lockedBy.map((s) => s.slug)).toEqual(['poster', 'figure']);
	});

	it('still offers the type`s current parent', () => {
		expect(parentChoices(all, t('poster', 'memo')).options.map((o) => o.slug)).toContain('memo');
	});
});

describe('inheritedFieldRows', () => {
	it('lists a parent`s live fields by title, falling back to the key', () => {
		const parent = {
			slug: 'memo',
			label: 'Memorabilia',
			attributes_schema: {
				type: 'object',
				properties: {
					condition: { type: 'string', title: 'Condition' },
					value: { type: 'number' },
					old: { type: 'string', title: 'Old', 'x-menagerist': { archived: true } }
				}
			}
		};
		expect(inheritedFieldRows(parent)).toEqual([
			{ key: 'condition', label: 'Condition' },
			{ key: 'value', label: 'value' }
		]);
	});

	it('is empty with no parent or no fields', () => {
		expect(inheritedFieldRows(null)).toEqual([]);
		const empty = { slug: 'a', label: 'A', attributes_schema: null };
		expect(inheritedFieldRows(empty)).toEqual([]);
	});
});

describe('inheritedFromParent', () => {
	const field = (title: string) => ({ type: 'string', title });
	const parent = { slug: 'memorabilia', label: 'Memorabilia', attributes_schema: null };
	const poster = {
		slug: 'poster',
		label: 'Poster',
		parent: 'memorabilia',
		attributes_schema: { type: 'object', properties: { width: field('Width') } },
		effective_schema: {
			type: 'object',
			properties: { condition: field('Condition'), width: field('Width') }
		}
	};

	it('names the parent and the fields it gives the subtype', () => {
		expect(inheritedFromParent(poster, [parent, poster])).toEqual({
			keys: ['condition'],
			label: 'Memorabilia'
		});
	});

	it('is null for a type with no parent, no inherited fields or a missing parent', () => {
		expect(inheritedFromParent(parent, [parent, poster])).toBeNull();
		expect(inheritedFromParent(null, [parent])).toBeNull();
		expect(inheritedFromParent(poster, [poster])).toBeNull();
		const bare = { ...poster, effective_schema: poster.attributes_schema };
		expect(inheritedFromParent(bare, [parent, bare])).toBeNull();
	});
});

describe('inheritedKeys', () => {
	const field = (title: string) => ({ type: 'string', title });

	it('lists the keys a subtype uses that it does not define itself, in order', () => {
		const poster = {
			attributes_schema: { type: 'object', properties: { width: field('Width') } },
			effective_schema: {
				type: 'object',
				properties: { condition: field('Condition'), value: field('Value'), width: field('Width') }
			}
		};
		expect(inheritedKeys(poster)).toEqual(['condition', 'value']);
	});

	it('is empty for a type with no parent, whose effective schema is its own', () => {
		const film = {
			attributes_schema: { type: 'object', properties: { rating: field('Rating') } },
			effective_schema: { type: 'object', properties: { rating: field('Rating') } }
		};
		expect(inheritedKeys(film)).toEqual([]);
	});

	it('is empty when the server gave no effective schema, or there is no type', () => {
		expect(inheritedKeys({ attributes_schema: { type: 'object', properties: {} } })).toEqual([]);
		expect(inheritedKeys(null)).toEqual([]);
		expect(inheritedKeys(undefined)).toEqual([]);
	});
});
