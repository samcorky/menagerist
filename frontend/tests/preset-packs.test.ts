import { describe, expect, it } from 'vitest';
import {
	canEditOptions,
	copyLabel,
	packKindMismatch,
	parsePackText,
	presetExampleSchema,
	visiblePresets,
	presetFilename
} from '../src/lib/preset-packs';

const preset = (overrides: Record<string, unknown>) =>
	({
		id: '0',
		kind: 'choice_list',
		label: 'Condition grades',
		definition: { options: ['Mint'] },
		version: 1,
		builtin: false,
		...overrides
	}) as never;

describe('copyLabel', () => {
	it('suffixes the label with (copy)', () => {
		expect(copyLabel('Condition grades')).toBe('Condition grades (copy)');
	});
});

describe('canEditOptions', () => {
	it('allows editing a custom list but never a built-in one', () => {
		expect(canEditOptions(preset({}))).toBe(true);
		expect(canEditOptions(preset({ builtin: true }))).toBe(false);
	});

	it('never offers options editing for fields or field groups', () => {
		expect(canEditOptions(preset({ kind: 'field' }))).toBe(false);
		expect(canEditOptions(preset({ kind: 'field_set' }))).toBe(false);
	});
});

describe('parsePackText', () => {
	it('accepts a menagerist-presets pack', () => {
		const pack = parsePackText('{"format":"menagerist-presets","version":1,"items":[]}');
		expect(pack.items).toEqual([]);
	});

	it('rejects text that is not JSON', () => {
		expect(() => parsePackText('not json')).toThrow("isn't valid JSON");
	});

	it('rejects JSON that is not a presets pack', () => {
		expect(() => parsePackText('{"format":"other","items":[]}')).toThrow(
			"isn't a Menagerist presets file"
		);
		expect(() => parsePackText('{"format":"menagerist-presets"}')).toThrow(
			"isn't a Menagerist presets file"
		);
	});
});

describe('packKindMismatch', () => {
	const pack = (kinds: string[]) =>
		({
			format: 'menagerist-presets',
			version: 1,
			items: kinds.map((kind) => ({ kind, label: 'x', definition: {} }))
		}) as never;

	it('is null when every item matches the section', () => {
		expect(packKindMismatch(pack(['choice_list', 'choice_list']), 'choice_list')).toBeNull();
	});

	it('names how many items do not fit a list section', () => {
		expect(packKindMismatch(pack(['choice_list', 'field']), 'choice_list')).toBe(
			'1 item in this file is not list'
		);
		expect(packKindMismatch(pack(['field', 'field_set']), 'choice_list')).toBe(
			'2 items in this file are not lists'
		);
	});
});

describe('presetFilename', () => {
	it('strips characters that are invalid in file names', () => {
		expect(presetFilename('Condition: grades/new')).toBe('Condition grades new.json');
		expect(presetFilename('   ')).toBe('preset.json');
	});
});

describe('presetExampleSchema', () => {
	it('previews a list as one choice field with the list as its options', () => {
		const schema = presetExampleSchema(
			preset({ label: 'Condition grades', definition: { options: ['Mint', 'Good'] } })
		);
		const [[key, property]] = Object.entries(schema.properties);
		expect(key).toBe('condition_grades');
		expect((property as { enum?: unknown }).enum).toEqual(['Mint', 'Good']);
		expect(property['x-menagerist']).toEqual({ kind: 'choice' });
	});

	it('previews a field group as one property per field, with unique keys', () => {
		const schema = presetExampleSchema(
			preset({
				kind: 'field_set',
				label: 'Purchase details',
				definition: {
					section: 'Purchase details',
					properties: [
						{ title: 'Date', type: 'string' },
						{ title: 'Date', type: 'string' }
					]
				}
			})
		);
		expect(Object.keys(schema.properties)).toEqual(['date', 'date_2']);
	});

	it('previews a single field with its own property', () => {
		const schema = presetExampleSchema(
			preset({
				kind: 'field',
				label: 'Rating',
				definition: { property: { title: 'Rating', type: 'number' } }
			})
		);
		expect(schema.properties.rating).toEqual({ title: 'Rating', type: 'number' });
	});
});

describe('built-in visibility', () => {
	it('filters built-ins out only when hidden', () => {
		const items = [
			{ label: 'Custom', builtin: false },
			{ label: 'Countries', builtin: true }
		];
		expect(visiblePresets(items, true)).toHaveLength(2);
		expect(visiblePresets(items, false)).toEqual([{ label: 'Custom', builtin: false }]);
	});
});
