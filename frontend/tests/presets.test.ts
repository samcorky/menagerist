import { describe, it, expect } from 'vitest';
import {
	fieldToDefinition,
	optionsToDefinition,
	definitionToField,
	listUpdateAvailable
} from '../src/lib/presets';
import type { EditorField } from '../src/lib/schema-types';

const field = (extra: Partial<EditorField> = {}): EditorField => ({
	key: 'condition',
	label: 'Condition',
	kind: 'choice',
	required: false,
	options: ['Mint', 'VG+'],
	subFields: [],
	...extra
});

describe('fieldToDefinition', () => {
	it('carries the property without a key', () => {
		const def = fieldToDefinition(field());
		expect(def.property).toEqual({
			title: 'Condition',
			type: 'string',
			enum: ['Mint', 'VG+'],
			'x-menagerist': { kind: 'choice' }
		});
	});

	it('drops archived and any earlier origin', () => {
		const def = fieldToDefinition(
			field({ meta: { archived: true, origin: { preset: 'old', version: 1 } } })
		);
		expect(def.property['x-menagerist']).toEqual({ kind: 'choice' });
	});

	it('keeps other metadata such as display', () => {
		const def = fieldToDefinition(field({ meta: { display: 'radio' } }));
		expect(def.property['x-menagerist']).toEqual({ kind: 'choice', display: 'radio' });
	});
});

describe('optionsToDefinition', () => {
	it('wraps the options array', () => {
		expect(optionsToDefinition(['A', 'B'])).toEqual({ options: ['A', 'B'] });
	});
});

describe('definitionToField', () => {
	it('produces a pending field with fresh provenance', () => {
		const def = fieldToDefinition(field());
		const result = definitionToField(def, { preset: 'p1', version: 3 });

		expect(result.keyPending).toBe(true);
		expect(result.kind).toBe('choice');
		expect(result.label).toBe('Condition');
		expect(result.options).toEqual(['Mint', 'VG+']);
		expect(result.meta?.origin).toEqual({ preset: 'p1', version: 3 });
	});
});

describe('listUpdateAvailable', () => {
	const preset = {
		id: 'p1',
		kind: 'choice_list' as const,
		label: 'Grades',
		description: null,
		definition: { options: ['Mint'] },
		version: 2,
		builtin: false
	};

	it('is true when the preset has a newer version than the field recorded', () => {
		const f = field({ meta: { origin: { preset: 'p1', version: 1 } } });
		expect(listUpdateAvailable(f, preset)).toBe(true);
	});

	it('is false when up to date, unlinked, or the preset is missing', () => {
		expect(
			listUpdateAvailable(field({ meta: { origin: { preset: 'p1', version: 2 } } }), preset)
		).toBe(false);
		expect(listUpdateAvailable(field(), preset)).toBe(false);
		expect(
			listUpdateAvailable(field({ meta: { origin: { preset: 'p1', version: 1 } } }), undefined)
		).toBe(false);
	});
});
