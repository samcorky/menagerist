import { describe, it, expect } from 'vitest';
import { allDescriptors } from '../src/lib/field-types/index';
import { fieldChips, flagsFor, setFlag, QUICK_CAPTURE_KINDS } from '../src/lib/field-flags';
import { fieldFromProperty, propertyFromField } from '../src/lib/field-types/registry';
import type { EditorField } from '../src/lib/schema-types';

const textField: EditorField = {
	key: 'isbn',
	label: 'ISBN',
	kind: 'text',
	required: false,
	options: [],
	subFields: []
};

describe('flagsFor', () => {
	it('offers quick capture on one-line kinds', () => {
		for (const kind of ['text', 'rating', 'multichoice']) {
			expect(flagsFor(kind).map((f) => f.member)).toContain('capture');
		}
	});

	it('offers nothing on kinds that need more room', () => {
		for (const kind of ['longtext', 'group', 'list', 'checklist', 'cron', 'opaque', 'timezone']) {
			expect(flagsFor(kind)).toEqual([]);
		}
	});

	it('lists the fourteen one-line kinds, all registered', () => {
		expect(QUICK_CAPTURE_KINDS.size).toBe(14);
		const registered = allDescriptors().map((d) => d.kind);
		for (const kind of QUICK_CAPTURE_KINDS) expect(registered).toContain(kind);
	});
});

describe('setFlag', () => {
	it('sets the member when switched on', () => {
		expect(setFlag(textField, 'capture', true).meta?.capture).toBe(true);
	});

	it('removes the member rather than writing false', () => {
		const on = setFlag(textField, 'capture', true);
		expect(setFlag(on, 'capture', false).meta).not.toHaveProperty('capture');
	});

	it('survives a round trip through the schema', () => {
		const prop = propertyFromField(setFlag(textField, 'capture', true));
		expect(fieldFromProperty('isbn', prop, false).meta?.capture).toBe(true);
	});
});

describe('fieldChips', () => {
	it('names what is switched on, Required first', () => {
		const field = setFlag({ ...textField, required: true }, 'capture', true);
		expect(fieldChips(field)).toEqual(['Required', 'Quick capture']);
	});

	it('ignores a flag the kind no longer offers', () => {
		const field = { ...setFlag(textField, 'capture', true), kind: 'longtext' };
		expect(fieldChips(field)).toEqual([]);
	});
});

describe('the barcode flag', () => {
	it('is offered on text fields only', () => {
		expect(flagsFor('text').map((f) => f.member)).toEqual(['capture', 'barcode']);
		expect(flagsFor('number').map((f) => f.member)).toEqual(['capture']);
	});

	it('shows as a Barcodes chip', () => {
		const field = setFlag(textField, 'barcode', true);
		expect(fieldChips(field)).toEqual(['Barcodes']);
	});
});
