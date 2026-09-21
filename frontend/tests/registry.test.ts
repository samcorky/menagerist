import { describe, it, expect, beforeEach } from 'vitest';
import {
	register,
	getDescriptor,
	allDescriptors,
	descriptorForProp,
	_clearRegistry,
	type FieldTypeDescriptor
} from '../src/lib/field-types/registry';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

// Minimal stub — Component type is complex; cast to satisfy the interface in tests.
const StubWidget = {} as FieldTypeDescriptor['InputWidget'];

const textDesc: FieldTypeDescriptor = {
	kind: 'text',
	label: 'Text',
	toSchema: (f) => ({ title: f.label, type: 'string' }),
	fromSchema: (key, prop, required) =>
		prop.type === 'string' && !('format' in prop) && !('enum' in prop)
			? { key, label: prop.title, kind: 'text', required, options: [], subFields: [] }
			: null,
	InputWidget: StubWidget
};

const numberDesc: FieldTypeDescriptor = {
	kind: 'number',
	label: 'Number',
	toSchema: (f) => ({ title: f.label, type: 'number' }),
	fromSchema: (key, prop, required) =>
		prop.type === 'number'
			? { key, label: prop.title, kind: 'number', required, options: [], subFields: [] }
			: null,
	InputWidget: StubWidget
};

beforeEach(() => {
	_clearRegistry();
});

describe('register / getDescriptor', () => {
	it('returns undefined for unknown kinds', () => {
		expect(getDescriptor('text')).toBeUndefined();
	});

	it('retrieves a registered descriptor by kind', () => {
		register(textDesc);
		expect(getDescriptor('text')).toBe(textDesc);
	});

	it('overwrites on duplicate registration', () => {
		register(textDesc);
		const updated = { ...textDesc, label: 'Updated' };
		register(updated);
		expect(getDescriptor('text')?.label).toBe('Updated');
	});
});

describe('allDescriptors', () => {
	it('returns empty array when registry is empty', () => {
		expect(allDescriptors()).toHaveLength(0);
	});

	it('returns all registered descriptors in insertion order', () => {
		register(textDesc);
		register(numberDesc);
		expect(allDescriptors().map((d) => d.kind)).toEqual(['text', 'number']);
	});
});

describe('descriptorForProp', () => {
	it('returns undefined when registry is empty', () => {
		expect(descriptorForProp({ title: 'X', type: 'string' })).toBeUndefined();
	});

	it('matches text descriptor for plain string prop', () => {
		register(textDesc);
		register(numberDesc);
		const result = descriptorForProp({ title: 'X', type: 'string' });
		expect(result?.kind).toBe('text');
	});

	it('matches number descriptor for number prop', () => {
		register(textDesc);
		register(numberDesc);
		const result = descriptorForProp({ title: 'X', type: 'number' });
		expect(result?.kind).toBe('number');
	});

	it('returns undefined when no descriptor matches', () => {
		register(numberDesc);
		// boolean prop, only number registered
		const prop: JsonSchemaProperty = { title: 'X', type: 'boolean' };
		expect(descriptorForProp(prop)).toBeUndefined();
	});
});
