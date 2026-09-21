import { describe, it, expect } from 'vitest';
import { allowedKinds, changeKind, kindChangeWarning } from '../src/lib/field-types/kind-changes';
import { staleChoice } from '../src/lib/field-types/choice/stale-choice';
import { fieldFromProperty } from '../src/lib/field-types';
import { optionRemovalWarning } from '../src/lib/field-usage';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

const ALL = ['text', 'longtext', 'number', 'rating', 'boolean', 'date', 'choice', 'group'];

describe('allowedKinds', () => {
	it('offers every kind for a field that has not been saved', () => {
		expect(allowedKinds(undefined, ALL)).toEqual(ALL);
	});

	it('lets text and longtext switch between each other only', () => {
		expect(allowedKinds('text', ALL)).toEqual(['text', 'longtext']);
		expect(allowedKinds('longtext', ALL)).toEqual(['text', 'longtext']);
	});

	it('lets number, boolean, date and choice become text or longtext', () => {
		for (const kind of ['number', 'boolean', 'date', 'choice']) {
			const allowed = allowedKinds(kind, ALL);
			expect(allowed).toContain('text');
			expect(allowed).toContain('longtext');
			expect(allowed).toContain(kind);
			expect(allowed).not.toContain('group');
		}
	});

	it('does not let text become number, boolean, date, choice or a group', () => {
		const allowed = allowedKinds('text', ALL);
		for (const kind of ['number', 'boolean', 'date', 'choice', 'group', 'rating']) {
			expect(allowed).not.toContain(kind);
		}
	});

	it('lets number and rating switch between each other', () => {
		expect(allowedKinds('number', ALL)).toContain('rating');
		expect(allowedKinds('rating', ALL)).toContain('number');
	});

	it('keeps groups as groups and unknown kinds as themselves', () => {
		expect(allowedKinds('group', ALL)).toEqual(['group']);
		expect(allowedKinds('plugin:thing', [...ALL, 'plugin:thing'])).toEqual(['plugin:thing']);
	});

	it('only offers kinds that are available', () => {
		expect(allowedKinds('number', ['number', 'text'])).toEqual(['number', 'text']);
	});
});

describe('kindChangeWarning', () => {
	it('warns when a number becomes a rating, and only then', () => {
		expect(kindChangeWarning('number', 'rating')).toMatch(/1 to 5/);
		expect(kindChangeWarning('rating', 'number')).toBeNull();
		expect(kindChangeWarning('text', 'longtext')).toBeNull();
		expect(kindChangeWarning(undefined, 'rating')).toBeNull();
	});
});

describe('changeKind', () => {
	const field = {
		kind: 'rating',
		meta: { kind: 'rating', display: 'stars', config: { a: 1 }, archived: false, future: 1 }
	};

	it('drops display and config but keeps the other metadata', () => {
		const next = changeKind(field, 'number');
		expect(next.kind).toBe('number');
		expect(next.meta).toEqual({ kind: 'rating', archived: false, future: 1 });
		expect(field.meta.display).toBe('stars');
	});

	it('returns the same field when the kind is unchanged', () => {
		expect(changeKind(field, 'rating')).toBe(field);
	});
});

describe('originalKind', () => {
	it('is the kind a field had when loaded from a saved schema', () => {
		const prop: JsonSchemaProperty = { title: 'Year', type: 'number' };
		expect(fieldFromProperty('year', prop, false).originalKind).toBe('number');
	});
});

describe('staleChoice', () => {
	it('returns a stored value that is no longer an option', () => {
		expect(staleChoice('Old', ['A', 'B'])).toBe('Old');
	});

	it('returns null for a current option, an empty value or a non-string', () => {
		expect(staleChoice('A', ['A', 'B'])).toBeNull();
		expect(staleChoice('', ['A'])).toBeNull();
		expect(staleChoice(undefined, ['A'])).toBeNull();
		expect(staleChoice(3, ['A'])).toBeNull();
	});
});

describe('optionRemovalWarning', () => {
	it('says how many are affected and what happens to them', () => {
		expect(optionRemovalWarning('Old', 3, 'node')).toBe(
			'“Old” is used by 3 items. They keep it, shown as (no longer an option).'
		);
		expect(optionRemovalWarning('Old', 1, 'edge')).toContain('1 connection.');
	});
});
