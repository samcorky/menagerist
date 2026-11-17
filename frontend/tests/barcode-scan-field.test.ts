import { describe, expect, it } from 'vitest';
import {
	NEW_BARCODE_DETAIL,
	scanFields,
	scannedAttributes,
	suggestScanField
} from '$lib/barcode/scan-field';
import type { AttributesSchema } from '$lib/schema-types';

function schema(properties: AttributesSchema['properties']): AttributesSchema {
	return {
		$schema: 'https://json-schema.org/draft/2020-12/schema',
		type: 'object',
		properties
	};
}

const BOOK = schema({
	author: { type: 'string', title: 'Author' },
	pages: { type: 'number', title: 'Pages' },
	isbn: { type: 'string', title: 'ISBN' },
	old_code: { type: 'string', title: 'Old code', 'x-menagerist': { archived: true } }
});

describe('scanFields', () => {
	it('offers the text fields a scanned code can go in, not numbers or archived fields', () => {
		expect(scanFields(BOOK)).toEqual([
			{ key: 'author', label: 'Author' },
			{ key: 'isbn', label: 'ISBN' }
		]);
	});

	it('offers nothing without a type', () => {
		expect(scanFields(null)).toEqual([]);
	});
});

describe('suggestScanField', () => {
	it.each([
		['ISBN', 'isbn'],
		['UPC', 'upc'],
		['EAN', 'ean'],
		['Barcode', 'barcode'],
		['ISBN-13', 'isbn_13']
	])('picks a field labelled %s', (label, key) => {
		expect(
			suggestScanField([
				{ key: 'author', label: 'Author' },
				{ key, label }
			])
		).toBe(key);
	});

	it('picks nothing when no label looks like a code', () => {
		expect(suggestScanField([{ key: 'author', label: 'Author' }])).toBeNull();
	});
});

describe('scannedAttributes', () => {
	it('fills only the chosen field', () => {
		expect(scannedAttributes('9780141036144', 'isbn', BOOK)).toEqual({
			attributes: { isbn: '9780141036144' },
			extraSchema: null
		});
	});

	it('adds a Barcode detail when no field was chosen', () => {
		const { attributes, extraSchema } = scannedAttributes(
			'0012345678905',
			NEW_BARCODE_DETAIL,
			null
		);
		expect(attributes).toEqual({ barcode: '0012345678905' });
		expect(extraSchema?.properties.barcode).toMatchObject({ type: 'string', title: 'Barcode' });
	});

	it('keeps the new detail clear of a field the type already has', () => {
		const typed = schema({ barcode: { type: 'number', title: 'Barcode number' } });
		const { attributes, extraSchema } = scannedAttributes('ABC-1', NEW_BARCODE_DETAIL, typed);
		expect(attributes).toEqual({ barcode_2: 'ABC-1' });
		expect(Object.keys(extraSchema?.properties ?? {})).toEqual(['barcode_2']);
	});
});
