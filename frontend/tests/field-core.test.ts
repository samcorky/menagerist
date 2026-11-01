import { describe, it, expect, beforeAll, beforeEach, afterAll } from 'vitest';
import '../src/lib/field-types';
import {
	_clearCores,
	allCores,
	coreForProp,
	getCore,
	registerCore,
	type FieldCore
} from '../src/lib/field-types/core';
import { allDescriptors, descriptorForProp, getDescriptor } from '../src/lib/field-types/registry';
import type { JsonSchemaProperty } from '../src/lib/json-schema';

const StubWidget = {} as FieldCore['InputWidget'];

/** A kind with no schema-editor half, chosen only by an explicit `kind`. */
const cronCore: FieldCore = {
	kind: 'test-schedule',
	label: 'Schedule',
	matches: (prop) => prop.type === 'string',
	rank: () => 0,
	InputWidget: StubWidget
};

// Other test files share the registry when isolation is off: restore it afterwards.
let originalCores: FieldCore[] = [];
beforeAll(() => {
	originalCores = allCores();
});
beforeEach(() => {
	registerCore(cronCore);
});
afterAll(() => {
	_clearCores();
	originalCores.forEach(registerCore);
});

describe('core and authoring registrations', () => {
	it('registers a core for every schema-editor kind', () => {
		for (const d of allDescriptors()) {
			const core = getCore(d.kind);
			expect(core, d.kind).toBeDefined();
			expect(core?.label).toBe(d.label);
			expect(core?.InputWidget).toBe(d.InputWidget);
		}
	});

	it('keeps editor-only members out of the core', () => {
		const core = getCore('text') as Record<string, unknown>;
		for (const member of ['toSchema', 'fromSchema', 'displayOptions', 'searchable']) {
			expect(member in core, member).toBe(false);
		}
	});

	it('lists a core-only kind in the core but not in the schema editor', () => {
		expect(allCores().map((c) => c.kind)).toContain('test-schedule');
		expect(getDescriptor('test-schedule')).toBeUndefined();
		expect(allDescriptors().map((d) => d.kind)).not.toContain('test-schedule');
	});
});

describe('matching', () => {
	const text: JsonSchemaProperty = { title: 'Name', type: 'string' };
	const cron: JsonSchemaProperty = {
		title: 'Schedule',
		type: 'string',
		'x-menagerist': { kind: 'test-schedule' }
	};

	it('picks a core-only kind by its explicit kind', () => {
		expect(coreForProp(cron)?.kind).toBe('test-schedule');
	});

	it('never lets a rank-0 kind win an unkinded property', () => {
		expect(coreForProp(text)?.kind).toBe('text');
	});

	it('agrees with the schema editor on every property it knows', () => {
		for (const prop of [text, { title: 'N', type: 'number' } as JsonSchemaProperty]) {
			expect(coreForProp(prop)?.kind).toBe(descriptorForProp(prop)?.kind);
		}
	});

	it('does not return a core-only kind from the schema editor lookup', () => {
		expect(descriptorForProp(cron)).toBeUndefined();
	});

	it('requires an explicit kind to still match the shape', () => {
		const wrongShape = { title: 'S', type: 'number', 'x-menagerist': { kind: 'test-schedule' } };
		expect(coreForProp(wrongShape as JsonSchemaProperty)).toBeUndefined();
	});
});
