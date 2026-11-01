import { describe, it, expect } from 'vitest';
import contract from '$shared/contracts/field-kinds.json';
import '../src/lib/field-types';
import { allDescriptors, getDescriptor } from '../src/lib/field-types/registry';
import { coreForProp, getCore } from '../src/lib/field-types/core';
import type { JsonSchemaProperty } from '../src/lib/json-schema';

// The backend may only hint a field kind listed in this file (see
// backend/tests/platform/test_settings_discovery.py); every one needs a widget here.

describe('field-kinds contract', () => {
	it.each(contract.kinds)('has a core widget for the %s kind', (kind) => {
		const core = getCore(kind);
		expect(core).toBeDefined();
		expect(core?.InputWidget).toBeDefined();
		expect(core?.ViewWidget).toBeDefined();
	});

	it.each(contract.kinds)('keeps %s out of the schema editor', (kind) => {
		expect(getDescriptor(kind)).toBeUndefined();
		expect(allDescriptors().map((d) => d.kind)).not.toContain(kind);
	});

	it('finds the cron widget from the hint the server sends', () => {
		const schedule = {
			type: 'string',
			title: 'Backup schedule',
			'x-menagerist': { kind: 'cron' }
		} as JsonSchemaProperty;
		expect(coreForProp(schedule)?.kind).toBe('cron');
	});

	it('does not offer the cron widget for plain text', () => {
		const text = { type: 'string', title: 'Name' } as JsonSchemaProperty;
		expect(coreForProp(text)?.kind).toBe('text');
	});

	it('ignores the cron hint on something that is not a string', () => {
		const wrong = { type: 'number', title: 'N', 'x-menagerist': { kind: 'cron' } };
		expect(coreForProp(wrong as JsonSchemaProperty)).toBeUndefined();
	});
});
