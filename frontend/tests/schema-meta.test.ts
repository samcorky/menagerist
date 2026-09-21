import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';
import { readPropMeta, readSchemaMeta, withPropMeta, withSchemaMeta } from '../src/lib/schema-meta';

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

describe('single accessor', () => {
	const srcDir = fileURLToPath(new URL('../src', import.meta.url));
	const allowed = new Set(['lib/schema-meta.ts', 'lib/schema-types.ts']);

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
			.filter((file) => !allowed.has(relative(srcDir, file)))
			.filter((file) => /x-menagerist|x-layout|x-multiline/.test(readFileSync(file, 'utf8')));
		expect(offenders.map((f) => relative(srcDir, f))).toEqual([]);
	});
});
