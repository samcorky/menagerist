import { describe, expect, it } from 'vitest';
import '../src/lib/field-types/index';
import { captureFieldKeys } from '$lib/quick-capture';
import type { AttributesSchema } from '$lib/schema-types';

const capture = (kind: string, extra: Record<string, unknown> = {}) => ({
	'x-menagerist': { kind, capture: true, ...extra }
});

describe('captureFieldKeys', () => {
	it('is empty without a type', () => {
		expect(captureFieldKeys(null)).toEqual([]);
	});

	it('keeps flagged one-line fields only', () => {
		const schema: AttributesSchema = {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties: {
				isbn: { type: 'string', title: 'ISBN', ...capture('text') },
				notes: { type: 'string', title: 'Notes', 'x-menagerist': { kind: 'text' } },
				blurb: { type: 'string', title: 'Blurb', ...capture('longtext') }
			}
		};
		expect(captureFieldKeys(schema)).toEqual(['isbn']);
	});

	it('leaves out archived fields', () => {
		const schema: AttributesSchema = {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties: {
				isbn: { type: 'string', title: 'ISBN', ...capture('text') },
				old: { type: 'string', title: 'Old', ...capture('text', { archived: true }) }
			}
		};
		expect(captureFieldKeys(schema)).toEqual(['isbn']);
	});

	it('follows display order, flattening sections', () => {
		const schema: AttributesSchema = {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties: {
				isbn: { type: 'string', title: 'ISBN', ...capture('text') },
				score: { type: 'number', title: 'Score', minimum: 1, maximum: 5, ...capture('rating') },
				year: { type: 'number', title: 'Year', ...capture('number') }
			},
			'x-menagerist': {
				version: 1,
				layout: [
					{ key: 'year' },
					{ id: 's1', section: 'Details', items: [{ key: 'score' }, { key: 'isbn' }] }
				]
			}
		};
		expect(captureFieldKeys(schema)).toEqual(['year', 'score', 'isbn']);
	});
});
