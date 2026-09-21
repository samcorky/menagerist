import { describe, it, expect } from 'vitest';
import '../src/lib/field-types/index';
import { matchContext } from '../src/lib/search-context';
import type { AttributesSchema } from '../src/lib/schema-types';

const schema = {
	$schema: 'https://json-schema.org/draft/2020-12/schema',
	type: 'object',
	properties: {
		director: { title: 'Director', type: 'string' },
		year: { title: 'Year', type: 'number' },
		seen: { title: 'Seen', type: 'boolean' },
		stars: {
			title: 'My rating',
			type: 'number',
			minimum: 1,
			maximum: 5,
			multipleOf: 1,
			'x-menagerist': { kind: 'rating' }
		},
		old: { title: 'Old', type: 'string', 'x-menagerist': { kind: 'text', archived: true } },
		internal: {
			title: 'Internal',
			type: 'string',
			'x-menagerist': { kind: 'text', search: false }
		},
		cast: {
			title: 'Cast',
			type: 'array',
			items: { type: 'object', properties: { name: { title: 'Name', type: 'string' } } }
		}
	}
} as unknown as AttributesSchema;

const film = {
	name: 'Alien',
	description: 'A xenomorph',
	attributes: {
		director: 'Ridley Scott',
		year: 1979,
		seen: true,
		stars: 5,
		old: 'gooey',
		internal: 'secret',
		cast: [{ name: 'Sigourney Weaver', role: 'Ripley' }],
		extra: 'Nostromo'
	}
};

describe('matchContext', () => {
	it('names the field and value for a string, a number and a table cell', () => {
		expect(matchContext(film, schema, 'scott')).toEqual({
			label: 'Director',
			text: 'Ridley Scott'
		});
		expect(matchContext(film, schema, '1979')).toEqual({ label: 'Year', text: '1979' });
		expect(matchContext(film, schema, 'weaver')).toEqual({
			label: 'Cast',
			text: 'Sigourney Weaver'
		});
	});

	it('uses the field name for details the type does not define, and for untyped items', () => {
		expect(matchContext(film, schema, 'nostromo')).toEqual({ label: 'extra', text: 'Nostromo' });
		expect(matchContext({ name: 'x', attributes: { note: 'hello' } }, null, 'ell')).toEqual({
			label: 'note',
			text: 'hello'
		});
	});

	it('is case-insensitive and ignores surrounding spaces', () => {
		expect(matchContext(film, schema, '  SCOTT ')?.label).toBe('Director');
	});

	it('returns null when the name or description matched, or the query is empty', () => {
		expect(matchContext(film, schema, 'alien')).toBeNull();
		expect(matchContext(film, schema, 'xeno')).toBeNull();
		expect(matchContext(film, schema, '')).toBeNull();
		expect(matchContext(film, schema, '   ')).toBeNull();
	});

	it('never matches keys, booleans, ratings, archived or opted-out fields', () => {
		for (const q of ['director', 'true', 'role', 'gooey', 'secret']) {
			expect(matchContext(film, schema, q), q).toBeNull();
		}
		expect(matchContext(film, schema, '5')).toBeNull();
	});

	it('handles items without attributes', () => {
		expect(matchContext({ name: 'x' }, schema, 'zzz')).toBeNull();
		expect(matchContext({ name: 'x', attributes: null }, null, 'zzz')).toBeNull();
	});

	it('does not read inherited property names', () => {
		expect(matchContext({ name: 'x', attributes: { constructor: 'abc' } }, schema, 'abc')).toEqual({
			label: 'constructor',
			text: 'abc'
		});
	});
});
