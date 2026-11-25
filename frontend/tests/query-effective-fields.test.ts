import { describe, expect, it } from 'vitest';
import { buildCatalogue, typeLabel } from '$lib/query/fields';

const field = (title: string) => ({ type: 'string', title });
const memorabilia = {
	slug: 'memorabilia',
	label: 'Memorabilia',
	attributes_schema: { type: 'object', properties: { condition: field('Condition') } }
};
const posterOwn = { type: 'object', properties: { width: field('Width') } };

describe('the field catalogue for a subtype', () => {
	it('lists the fields its parent shares as well as its own', () => {
		const poster = {
			slug: 'poster',
			label: 'Poster',
			attributes_schema: posterOwn,
			effective_schema: {
				type: 'object',
				properties: { condition: field('Condition'), width: field('Width') }
			}
		};

		const { fields } = buildCatalogue([memorabilia, poster]);

		expect(fields.filter((f) => f.type === 'poster').map((f) => f.key)).toEqual([
			'condition',
			'width'
		]);
		expect(fields.filter((f) => f.type === 'memorabilia').map((f) => f.key)).toEqual(['condition']);
	});

	it('lists only a type`s own fields when the server gave no effective schema', () => {
		const poster = { slug: 'poster', label: 'Poster', attributes_schema: posterOwn };

		const { fields } = buildCatalogue([poster]);

		expect(fields.map((f) => f.key)).toEqual(['width']);
	});
});

describe('naming a subtype in a chip', () => {
	it('shows it with its parent, and a top-level type as it is', () => {
		const poster = { slug: 'poster', label: 'Poster', parent: 'memorabilia' };
		const catalogue = buildCatalogue([memorabilia, poster]);

		expect(typeLabel(catalogue, 'poster')).toBe('Memorabilia › Poster');
		expect(typeLabel(catalogue, 'memorabilia')).toBe('Memorabilia');
		expect(typeLabel(catalogue, 'gone')).toBe('gone');
	});
});
