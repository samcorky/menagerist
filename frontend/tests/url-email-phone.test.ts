import { describe, it, expect } from 'vitest';
import {
	getDescriptor,
	descriptorForProp,
	fieldFromProperty,
	propertyFromField
} from '../src/lib/field-types';
import { PHONE_PATTERN } from '../src/lib/field-types/phone/phone';
import type { JsonSchemaProperty } from '../src/lib/schema-types';

describe('url', () => {
	const urlProp = {
		title: 'Website',
		type: 'string',
		format: 'uri',
		'x-menagerist': { kind: 'url' }
	} as JsonSchemaProperty;

	it('is registered and matches a string with format: uri', () => {
		expect(getDescriptor('url')).toBeDefined();
		expect(descriptorForProp(urlProp)?.kind).toBe('url');
	});

	it('round-trips through toSchema/fromSchema unchanged', () => {
		expect(propertyFromField(fieldFromProperty('website', urlProp, false))).toEqual(urlProp);
	});

	it('is a group sub-field and highlightable', () => {
		const desc = getDescriptor('url')!;
		expect(desc.canBeSubField).toBe(true);
		expect(desc.highlightable).toBe(true);
	});
});

describe('email', () => {
	const emailProp = {
		title: 'Contact email',
		type: 'string',
		format: 'email',
		'x-menagerist': { kind: 'email' }
	} as JsonSchemaProperty;

	it('is registered and matches a string with format: email', () => {
		expect(getDescriptor('email')).toBeDefined();
		expect(descriptorForProp(emailProp)?.kind).toBe('email');
	});

	it('round-trips through toSchema/fromSchema unchanged', () => {
		expect(propertyFromField(fieldFromProperty('contact_email', emailProp, false))).toEqual(
			emailProp
		);
	});

	it('is a group sub-field and highlightable', () => {
		const desc = getDescriptor('email')!;
		expect(desc.canBeSubField).toBe(true);
		expect(desc.highlightable).toBe(true);
	});
});

describe('phone', () => {
	const phoneProp = {
		title: 'Phone number',
		type: 'string',
		pattern: PHONE_PATTERN,
		'x-menagerist': { kind: 'phone' }
	} as JsonSchemaProperty;

	it('is registered and matches its exact pattern', () => {
		expect(getDescriptor('phone')).toBeDefined();
		expect(descriptorForProp(phoneProp)?.kind).toBe('phone');
	});

	it('does not match a different pattern, which falls through to text', () => {
		const otherPattern = { title: 'Code', type: 'string', pattern: '^[A-Z]{3}$' };
		expect(descriptorForProp(otherPattern as unknown as JsonSchemaProperty)?.kind).toBe('text');
	});

	it('round-trips through toSchema/fromSchema unchanged', () => {
		expect(propertyFromField(fieldFromProperty('phone_number', phoneProp, false))).toEqual(
			phoneProp
		);
	});

	it('is a group sub-field and highlightable', () => {
		const desc = getDescriptor('phone')!;
		expect(desc.canBeSubField).toBe(true);
		expect(desc.highlightable).toBe(true);
	});
});

describe('an unrecognised string format falls back to opaque', () => {
	it('does not match url, email or phone for an unknown format', () => {
		const prop = {
			title: 'X',
			type: 'string',
			format: 'hostname'
		} as unknown as JsonSchemaProperty;
		expect(descriptorForProp(prop)).toBeUndefined();
		expect(fieldFromProperty('x', prop, false).kind).toBe('opaque');
	});
});
