import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';
import { Validator } from '@cfworker/json-schema';
import {
	archivedKeys,
	mergeAttributeSchemas,
	readPropMeta,
	readSchemaMeta,
	validationSchema,
	withPropMeta,
	withSchemaMeta
} from '../src/lib/schema-meta';
import type { AttributesSchema } from '../src/lib/schema-types';

describe('readers', () => {
	it('return {} when the namespace is absent or malformed', () => {
		expect(readSchemaMeta({})).toEqual({});
		expect(readSchemaMeta(null)).toEqual({});
		expect(readPropMeta({ 'x-menagerist': 'nope' })).toEqual({});
		expect(readPropMeta({ 'x-menagerist': [1] })).toEqual({});
	});

	it('return a copy that preserves unknown members', () => {
		const schema = { 'x-menagerist': { version: 1, highlights: ['a'], future: true } };
		const meta = readSchemaMeta(schema);
		expect(meta).toEqual(schema['x-menagerist']);
		expect(meta).not.toBe(schema['x-menagerist']);
	});
});

describe('writers', () => {
	it('withPropMeta merges into existing metadata without mutating the input', () => {
		const prop = { title: 'X', 'x-menagerist': { kind: 'text', future: 1 } };
		const next = withPropMeta(prop, { display: 'stars' });
		expect(readPropMeta(next)).toEqual({ kind: 'text', future: 1, display: 'stars' });
		expect(readPropMeta(prop)).toEqual({ kind: 'text', future: 1 });
	});

	it('withSchemaMeta writes version, layout and required', () => {
		const next = withSchemaMeta({ type: 'object' }, { version: 1, layout: [{ key: 'a' }] });
		expect(readSchemaMeta(next)).toEqual({ version: 1, layout: [{ key: 'a' }] });
	});
});

describe('validationSchema', () => {
	const schema = {
		$schema: 'https://json-schema.org/draft/2020-12/schema',
		type: 'object',
		properties: { year: { title: 'Year', type: 'number' } },
		required: ['year'],
		'x-menagerist': { required: ['year'] }
	};

	it('drops a standard root required array without mutating the input', () => {
		expect(validationSchema(schema)).not.toHaveProperty('required');
		expect(schema.required).toEqual(['year']);
	});

	it('never turns a missing required field into an error', () => {
		const strict = new Validator(schema as object, '2020-12', false);
		const advisory = new Validator(validationSchema(schema) as object, '2020-12', false);
		expect(strict.validate({}).valid).toBe(false);
		expect(advisory.validate({}).valid).toBe(true);
		expect(advisory.validate({ year: 'x' }).valid).toBe(false);
	});
});

describe('archived properties', () => {
	const schema = {
		properties: {
			year: { type: 'number' },
			old: { type: 'string', 'x-menagerist': { archived: true } },
			live: { type: 'string', 'x-menagerist': { archived: false } }
		}
	};

	it('archivedKeys lists only archived top-level properties', () => {
		expect([...archivedKeys(schema)]).toEqual(['old']);
		expect(archivedKeys(null).size).toBe(0);
	});

	it('validationSchema drops archived properties so their values are never checked', () => {
		const withArchived = { ...schema, type: 'object' };
		const v = new Validator(validationSchema(withArchived) as object, '2020-12', false);
		expect(v.validate({ old: 5 }).valid).toBe(true);
		expect(v.validate({ year: 'x' }).valid).toBe(false);
		expect(Object.keys(withArchived.properties)).toContain('old');
	});
});

describe('single accessor', () => {
	const srcDir = fileURLToPath(new URL('../src', import.meta.url));
	const allowed = new Set(['lib/schema-meta.ts', 'lib/schema-types.ts']);
	const rel = (file: string) => relative(srcDir, file).replaceAll('\\', '/');

	function sourceFiles(dir: string): string[] {
		return readdirSync(dir).flatMap((name) => {
			const path = join(dir, name);
			if (path.includes(join('lib', 'api', 'generated'))) return [];
			if (statSync(path).isDirectory()) return sourceFiles(path);
			return /\.(ts|svelte)$/.test(name) ? [path] : [];
		});
	}

	it('no code outside the accessor and its types reads x-* keywords', () => {
		const offenders = sourceFiles(srcDir)
			.filter((file) => !allowed.has(rel(file)))
			.filter((file) => /x-menagerist|x-layout|x-multiline/.test(readFileSync(file, 'utf8')));
		expect(offenders.map(rel)).toEqual([]);
	});
});

describe('mergeAttributeSchemas', () => {
	const schema = (properties: AttributesSchema['properties']): AttributesSchema => ({
		$schema: 'https://json-schema.org/draft/2020-12/schema',
		type: 'object',
		properties
	});

	it('returns null when both schemas are null', () => {
		expect(mergeAttributeSchemas(null, null)).toBeNull();
	});

	it('returns the type schema unchanged when there is no overlay', () => {
		const type = schema({ title: { title: 'Title', type: 'string' } });
		expect(mergeAttributeSchemas(type, null)).toEqual(type);
	});

	it('returns the overlay as the schema when there is no type', () => {
		const extra = schema({ condition: { title: 'Condition', type: 'string' } });
		expect(mergeAttributeSchemas(null, extra)).toEqual(extra);
	});

	it('merges properties from both schemas', () => {
		const type = schema({ title: { title: 'Title', type: 'string' } });
		const extra = schema({ condition: { title: 'Condition', type: 'string' } });
		const merged = mergeAttributeSchemas(type, extra);
		expect(Object.keys(merged?.properties ?? {}).sort()).toEqual(['condition', 'title']);
	});

	it('concatenates required and layout, type fields first', () => {
		const type = withSchemaMeta(schema({ title: { title: 'Title', type: 'string' } }), {
			required: ['title'],
			layout: [{ key: 'title' }]
		});
		const extra = withSchemaMeta(schema({ condition: { title: 'Condition', type: 'string' } }), {
			required: ['condition'],
			layout: [{ key: 'condition' }]
		});
		const merged = mergeAttributeSchemas(type, extra);
		expect(readSchemaMeta(merged).required).toEqual(['title', 'condition']);
		expect(readSchemaMeta(merged).layout).toEqual([{ key: 'title' }, { key: 'condition' }]);
	});

	it('throws when a key is defined on both schemas', () => {
		const type = schema({ condition: { title: 'Condition', type: 'string' } });
		const extra = schema({ condition: { title: 'Condition 2', type: 'string' } });
		expect(() => mergeAttributeSchemas(type, extra)).toThrow();
	});
});
