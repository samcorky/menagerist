import { readFileSync } from 'node:fs';
import { describe, it, expect } from 'vitest';
import { Validator } from '@cfworker/json-schema';
import {
	constraintKeywords,
	describeConstraints,
	describePattern,
	escapeLiteral,
	parseConstraints,
	unescapeLiteral
} from '../src/lib/field-types/text/constraints';
import { fieldFromProperty, propertyFromField } from '../src/lib/field-types/index';
import { rowsToAttributes } from '../src/lib/attribute-rows';
import { createSafeValidator, stripPatterns } from '../src/lib/safe-validator';
import {
	friendlyClientError,
	friendlyServerError,
	serverErrorsToFields,
	topLevelKey
} from '../src/lib/validation-messages';
import type { AttributesSchema, EditorField, JsonSchemaProperty } from '../src/lib/schema-types';

const AWKWARD = [
	'.',
	'/',
	'(',
	')',
	'[',
	']',
	'{1}',
	'a|b',
	'^x$',
	'back\\slash',
	'a-b',
	'a+b*c?',
	'café',
	'🎵 song',
	'日本語'
];

function schemaWith(prop: Record<string, unknown>): AttributesSchema {
	return {
		$schema: 'https://json-schema.org/draft/2020-12/schema',
		type: 'object',
		properties: {
			cover_file: { title: 'Cover file', type: 'string', ...prop, 'x-menagerist': { kind: 'text' } }
		}
	} as AttributesSchema;
}

function textField(config?: Record<string, unknown>): EditorField {
	return {
		key: 'cover_file',
		label: 'Cover file',
		kind: 'text',
		required: false,
		options: [],
		subFields: [],
		...(config ? { config } : {})
	};
}

describe('escapeLiteral', () => {
	it('round-trips awkward literals', () => {
		for (const text of AWKWARD) expect(unescapeLiteral(escapeLiteral(text))).toBe(text);
	});

	it('never escapes a hyphen (invalid under the u flag)', () => {
		expect(escapeLiteral('a-b')).toBe('a-b');
	});

	it('escapes every syntax character', () => {
		expect(escapeLiteral('.jpg')).toBe('\\.jpg');
		expect(escapeLiteral('a/b')).toBe('a\\/b');
	});

	it('rejects text that escapeLiteral would not produce', () => {
		expect(unescapeLiteral('a.b')).toBeNull();
		expect(unescapeLiteral('a\\-b')).toBeNull();
		expect(unescapeLiteral('a\\')).toBeNull();
		expect(unescapeLiteral('\\d')).toBeNull();
	});
});

describe('constraintKeywords', () => {
	it('emits nothing without constraints', () => {
		expect(constraintKeywords({})).toEqual({});
		expect(constraintKeywords({ startsWith: '', endsWith: '' })).toEqual({});
	});

	it('emits one pattern for a prefix or a suffix', () => {
		expect(constraintKeywords({ startsWith: 'cover-' })).toEqual({ pattern: '^cover-' });
		expect(constraintKeywords({ endsWith: '.jpg' })).toEqual({ pattern: '\\.jpg$' });
	});

	it('emits an allOf of two patterns for both, including identical ones', () => {
		expect(constraintKeywords({ startsWith: 'cover-', endsWith: '.jpg' })).toEqual({
			allOf: [{ pattern: '^cover-' }, { pattern: '\\.jpg$' }]
		});
		expect(constraintKeywords({ startsWith: 'a', endsWith: 'a' })).toEqual({
			allOf: [{ pattern: '^a' }, { pattern: 'a$' }]
		});
	});
});

describe('parseConstraints', () => {
	it('reads back what the writer emits', () => {
		for (const c of [
			{ startsWith: 'cover-', endsWith: '' },
			{ startsWith: '', endsWith: '.jpg' },
			{ startsWith: 'cover-', endsWith: '.jpg' },
			{ startsWith: 'a', endsWith: 'a' },
			...AWKWARD.map((t) => ({ startsWith: t, endsWith: t }))
		]) {
			expect(parseConstraints(constraintKeywords(c))).toEqual({ constraints: c, custom: null });
		}
	});

	it('reports nothing for a property without patterns', () => {
		expect(parseConstraints({})).toEqual({
			constraints: { startsWith: '', endsWith: '' },
			custom: null
		});
	});

	it('treats other patterns as custom and keeps them as written', () => {
		for (const prop of [
			{ pattern: '^\\d{4}$' },
			{ pattern: '^a$' },
			{ pattern: 'a\\-b$' },
			{ allOf: [{ pattern: '^a' }] },
			{ allOf: [{ pattern: '^a' }, { minLength: 3 }] },
			{ allOf: [{ pattern: 'b$' }, { pattern: '^a' }] },
			{ pattern: '^a', allOf: [{ pattern: 'b$' }] }
		]) {
			const parsed = parseConstraints(prop);
			expect(parsed.custom).toEqual(prop);
			expect(parsed.constraints).toEqual({ startsWith: '', endsWith: '' });
		}
	});
});

describe('friendly messages', () => {
	it('words a generated pattern from the pattern itself', () => {
		expect(describePattern('^cover-')).toBe('Must start with "cover-"');
		expect(describePattern('\\.jpg$')).toBe('Must end with ".jpg"');
		expect(describePattern('^\\d+$')).toBeNull();
		expect(describePattern(42)).toBeNull();
	});

	it('describes the rule as helper text', () => {
		expect(describeConstraints({ startsWith: 'cover-', endsWith: '.jpg' })).toBe(
			'Must start with "cover-" and end with ".jpg"'
		);
		expect(describeConstraints({ endsWith: '.jpg' })).toBe('Must end with ".jpg"');
		expect(describeConstraints({})).toBeNull();
	});

	const schema = schemaWith({
		allOf: [{ pattern: '^cover-' }, { pattern: '\\.jpg$' }]
	});

	it('translates each failing half of a client error, in either order', () => {
		const errors = createSafeValidator(schema as unknown as Record<string, unknown>).validate({
			cover_file: 'x.png'
		});
		const messages = errors
			.filter((e) => e.keyword === 'pattern')
			.map((e) => friendlyClientError(schema, e));
		expect(messages.sort()).toEqual(['Must end with ".jpg"', 'Must start with "cover-"']);
	});

	it('translates a server error using its keyword and value', () => {
		expect(
			friendlyServerError(schema, {
				path: '/cover_file',
				message: 'no match',
				keyword: 'pattern',
				value: '^cover-'
			})
		).toBe('Must start with "cover-"');
	});

	it('falls back to the raw message for other keywords and custom patterns', () => {
		expect(
			friendlyServerError(schema, {
				path: '/cover_file',
				message: 'too long',
				keyword: 'maxLength',
				value: 3
			})
		).toBe('too long');
		expect(
			friendlyServerError(schema, {
				path: '/cover_file',
				message: 'raw',
				keyword: 'pattern',
				value: '^\\d+$'
			})
		).toBe('raw');
		expect(friendlyServerError(null, { path: '/x', message: 'raw' })).toBe('raw');
	});

	it('finds a text sub-field inside a table and maps errors to the top-level field', () => {
		const table = {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties: {
				tracks: {
					title: 'Tracks',
					type: 'array',
					items: {
						type: 'object',
						properties: { code: { title: 'Code', type: 'string', pattern: '^LP-' } }
					}
				}
			}
		} as unknown as AttributesSchema;
		const fields = serverErrorsToFields(table, [
			{ path: '/tracks/0/code', message: 'no', keyword: 'pattern', value: '^LP-' },
			{ path: '/tracks/1/code', message: 'second' },
			{ path: '/', message: 'root' }
		]);
		expect(fields).toEqual({ tracks: 'Must start with "LP-"' });
		expect(topLevelKey('#/tracks/0/code')).toBe('tracks');
		expect(topLevelKey('/cover_file')).toBe('cover_file');
	});
});

describe('text descriptor', () => {
	const bothProp = {
		title: 'Cover file',
		type: 'string',
		allOf: [{ pattern: '^cover-' }, { pattern: '\\.jpg$' }],
		'x-menagerist': { kind: 'text' }
	} as JsonSchemaProperty;

	it('saves a prefix and suffix as the documented schema and reloads the same inputs', () => {
		const written = propertyFromField(textField({ startsWith: 'cover-', endsWith: '.jpg' }));
		expect(written).toEqual(bothProp);
		const field = fieldFromProperty('cover_file', written, false);
		expect(field.kind).toBe('text');
		expect(field.config).toEqual({ startsWith: 'cover-', endsWith: '.jpg' });
	});

	it('adds no keywords or config when there are no constraints', () => {
		const written = propertyFromField(textField());
		expect(written).toEqual({
			title: 'Cover file',
			type: 'string',
			'x-menagerist': { kind: 'text' }
		});
		expect(fieldFromProperty('cover_file', written, false).config).toBeUndefined();
	});

	it('clearing both inputs removes the keywords', () => {
		const written = propertyFromField(textField({ startsWith: '', endsWith: '' }));
		expect(written).not.toHaveProperty('pattern');
		expect(written).not.toHaveProperty('allOf');
	});

	it('keeps a custom pattern unchanged through open-edit-save', () => {
		const prop = {
			title: 'Year',
			type: 'string',
			pattern: '^\\d{4}$',
			'x-menagerist': { kind: 'text' }
		} as JsonSchemaProperty;
		const field = fieldFromProperty('year', prop, false);
		expect(field.kind).toBe('text');
		expect(propertyFromField({ ...field, label: 'Release year' })).toEqual({
			...prop,
			title: 'Release year'
		});
	});

	it('applies to text sub-fields inside a group', () => {
		const group = {
			title: 'Tracks',
			type: 'array',
			items: {
				type: 'object',
				properties: {
					code: {
						title: 'Code',
						type: 'string',
						pattern: '^LP-',
						'x-menagerist': { kind: 'text' }
					}
				}
			},
			'x-menagerist': { kind: 'group' }
		} as unknown as JsonSchemaProperty;
		const field = fieldFromProperty('tracks', group, false);
		expect(field.subFields[0].config).toEqual({ startsWith: 'LP-', endsWith: '' });
		expect(propertyFromField(field)).toEqual(group);
	});

	it('never generates a pattern cfworker rejects', () => {
		for (const text of AWKWARD) {
			const prop = constraintKeywords({ startsWith: text, endsWith: text });
			const validator = new Validator(schemaWith(prop) as unknown as object, '2020-12', false);
			expect(() => validator.validate({ cover_file: text + 'mid' + text })).not.toThrow();
			expect(validator.validate({ cover_file: text + 'mid' + text }).valid).toBe(true);
			expect(validator.validate({ cover_file: 'nothing' }).valid).toBe(false);
		}
	});
});

describe('empty constrained values', () => {
	it('omits an empty optional text field that has a pattern', () => {
		const schema = schemaWith({ pattern: '^cover-' });
		expect(rowsToAttributes([{ key: 'cover_file', value: '' }], schema)).toEqual({});
		expect(rowsToAttributes([{ key: 'cover_file', value: 'cover-a.jpg' }], schema)).toEqual({
			cover_file: 'cover-a.jpg'
		});
	});

	it('omits it when the constraint is an allOf', () => {
		const schema = schemaWith({ allOf: [{ pattern: '^a' }, { pattern: 'b$' }] });
		expect(rowsToAttributes([{ key: 'cover_file', value: '' }], schema)).toEqual({});
	});

	it('still keeps an empty unconstrained text field as an empty string', () => {
		expect(rowsToAttributes([{ key: 'cover_file', value: '' }], schemaWith({}))).toEqual({
			cover_file: ''
		});
	});

	it('omits an empty constrained cell in a group row', () => {
		const schema = {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties: {
				tracks: {
					title: 'Tracks',
					type: 'array',
					items: {
						type: 'object',
						properties: {
							code: { title: 'Code', type: 'string', pattern: '^LP-' },
							name: { title: 'Name', type: 'string' }
						}
					}
				}
			}
		} as unknown as AttributesSchema;
		expect(rowsToAttributes([{ key: 'tracks', value: [{ code: '', name: '' }] }], schema)).toEqual({
			tracks: [{ name: '' }]
		});
	});
});

describe('safe validator', () => {
	const badSchema = schemaWith({ pattern: '(?<' });

	it('does not throw when a pattern is not valid JavaScript, and skips only pattern rules', () => {
		const validator = createSafeValidator(badSchema as unknown as Record<string, unknown>);
		expect(() => validator.validate({ cover_file: 'x' })).not.toThrow();
		expect(validator.degraded).toBe(true);
		expect(validator.validate({ cover_file: 5 }).length).toBeGreaterThan(0);
	});

	it('is not degraded for valid patterns', () => {
		const validator = createSafeValidator(
			schemaWith({ pattern: '^a' }) as unknown as Record<string, unknown>
		);
		expect(validator.validate({ cover_file: 'b' }).some((e) => e.keyword === 'pattern')).toBe(true);
		expect(validator.degraded).toBe(false);
	});

	it('strips patterns but keeps a property that is named pattern', () => {
		const stripped = stripPatterns({
			type: 'object',
			properties: {
				pattern: { type: 'string', pattern: '(?<' },
				other: { type: 'string', allOf: [{ pattern: 'x' }] }
			}
		}) as { properties: Record<string, Record<string, unknown>> };
		expect(stripped.properties.pattern).toEqual({ type: 'string' });
		expect(stripped.properties.other).toEqual({ type: 'string' });
	});
});

describe('regex conformance fixture', () => {
	const fixture = JSON.parse(
		readFileSync(
			new URL('../../contract/fixtures/regex-conformance.json', import.meta.url),
			'utf-8'
		)
	) as { cases: { pattern: string; value: string; expected: boolean }[] };

	it('agrees with JavaScript (the backend suite checks Python)', () => {
		expect(fixture.cases.length).toBeGreaterThan(0);
		for (const c of fixture.cases) {
			const validator = new Validator(
				{ type: 'string', pattern: c.pattern } as object,
				'2020-12',
				false
			);
			expect(validator.validate(c.value).valid, JSON.stringify(c)).toBe(c.expected);
		}
	});

	it('is what the writer produces for its own simple cases', () => {
		expect(constraintKeywords({ startsWith: 'cover-' }).pattern).toBe('^cover-');
		expect(constraintKeywords({ endsWith: '.jpg' }).pattern).toBe('\\.jpg$');
	});
});
