import { describe, expect, it } from 'vitest';
import {
	canEditOptions,
	bundleKindMismatch,
	parseBundleText,
	presetExampleSchema,
	presetFilename
} from '../src/lib/preset-packs';

const preset = (overrides: Record<string, unknown>) =>
	({
		id: '0',
		kind: 'choice_list',
		label: 'Condition grades',
		definition: { options: ['Mint'] },
		version: 1,
		...overrides
	}) as never;

describe('canEditOptions', () => {
	it('allows editing a choice list', () => {
		expect(canEditOptions(preset({}))).toBe(true);
	});

	it('never offers options editing for fields or field groups', () => {
		expect(canEditOptions(preset({ kind: 'field' }))).toBe(false);
		expect(canEditOptions(preset({ kind: 'field_set' }))).toBe(false);
	});
});

describe('parseBundleText', () => {
	it('accepts a menagerist-bundle file', () => {
		const bundle = parseBundleText('{"format":"menagerist-bundle","version":1,"presets":[]}');
		expect(bundle.presets).toEqual([]);
	});

	it('rejects text that is not JSON', () => {
		expect(() => parseBundleText('not json')).toThrow("isn't valid JSON");
	});

	it('rejects JSON that is not a bundle file, the old presets format included', () => {
		expect(() => parseBundleText('{"format":"other","presets":[]}')).toThrow(
			"isn't a Menagerist saved fields file"
		);
		expect(() => parseBundleText('{"format":"menagerist-presets","version":1,"items":[]}')).toThrow(
			"isn't a Menagerist saved fields file"
		);
		expect(() => parseBundleText('{"format":"menagerist-bundle"}')).toThrow(
			"isn't a Menagerist saved fields file"
		);
	});
});

describe('bundleKindMismatch', () => {
	const pack = (kinds: string[]) =>
		({
			format: 'menagerist-bundle',
			version: 1,
			presets: kinds.map((kind, n) => ({ ref: `p-${n}`, kind, label: 'x', definition: {} }))
		}) as never;

	it('is null when every item matches the section', () => {
		expect(bundleKindMismatch(pack(['choice_list', 'choice_list']), 'choice_list')).toBeNull();
	});

	it('names how many items do not fit a list section', () => {
		expect(bundleKindMismatch(pack(['choice_list', 'field']), 'choice_list')).toBe(
			'1 item in this file is not a list'
		);
		expect(bundleKindMismatch(pack(['field', 'field_set']), 'choice_list')).toBe(
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
