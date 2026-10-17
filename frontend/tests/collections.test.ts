import { describe, expect, it } from 'vitest';
import {
	MAX_COLLECTION_NAME_LENGTH,
	addItemsErrorMessage,
	canonicalSlugFor,
	collectionRouteParams,
	collectionSaveErrorMessage,
	slugPatch,
	slugSaveErrorMessage,
	describeAddResult,
	describeItemCount,
	validateCollectionName
} from '$lib/collections';

describe('describeItemCount', () => {
	it('words zero, one and many', () => {
		expect(describeItemCount(0)).toBe('No items');
		expect(describeItemCount(1)).toBe('1 item');
		expect(describeItemCount(12)).toBe('12 items');
	});
});

describe('describeAddResult', () => {
	it('reports everything added', () => {
		expect(describeAddResult(1, 1)).toBe('Added 1 item');
		expect(describeAddResult(3, 3)).toBe('Added 3 items');
	});
	it('reports how many were already there', () => {
		expect(describeAddResult(2, 3)).toBe('Added 2 items. 1 was already there');
		expect(describeAddResult(1, 4)).toBe('Added 1 item. 3 were already there');
	});
	it('reports nothing new', () => {
		expect(describeAddResult(0, 1)).toBe('That item is already there');
		expect(describeAddResult(0, 3)).toBe('Those items are already there');
	});
});

describe('addItemsErrorMessage', () => {
	it('maps the statuses the server uses', () => {
		expect(addItemsErrorMessage(400)).toBe(
			'Some of those items no longer exist. Refresh and try again.'
		);
		expect(addItemsErrorMessage(404)).toBe('This collection no longer exists.');
		expect(addItemsErrorMessage(422)).toBe('You can add up to 500 items at a time.');
	});
	it('falls back for anything else', () => {
		expect(addItemsErrorMessage(500)).toBe("Couldn't add those items. Try again.");
		expect(addItemsErrorMessage(undefined)).toBe("Couldn't add those items. Try again.");
	});
});

describe('validateCollectionName', () => {
	it('accepts a normal name and trims before counting', () => {
		expect(validateCollectionName('My vinyl')).toBeNull();
		expect(validateCollectionName(`  ${'a'.repeat(MAX_COLLECTION_NAME_LENGTH)}  `)).toBeNull();
	});
	it('rejects blank and over-long names', () => {
		expect(validateCollectionName('   ')).toBe('Give the collection a name.');
		expect(validateCollectionName('a'.repeat(MAX_COLLECTION_NAME_LENGTH + 1))).toBe(
			'Names can be up to 120 characters.'
		);
	});
});

describe('collectionSaveErrorMessage', () => {
	it('maps validation, conflict and missing', () => {
		expect(collectionSaveErrorMessage(400)).toBe(
			'That name is not valid. Use 1 to 120 characters.'
		);
		expect(collectionSaveErrorMessage(422)).toBe(
			'That name is not valid. Use 1 to 120 characters.'
		);
		expect(collectionSaveErrorMessage(409)).toBe(
			'A collection with that link name already exists.'
		);
		expect(collectionSaveErrorMessage(404)).toBe('This collection no longer exists.');
		expect(collectionSaveErrorMessage(500)).toBe("Couldn't save the collection. Try again.");
	});
});

describe('canonicalSlugFor', () => {
	const loaded = { id: '0190-aaaa', slug: 'my-films' };
	it('asks for the slug when the address uses the id', () => {
		expect(canonicalSlugFor('0190-aaaa', loaded)).toBe('my-films');
	});
	it('asks for the slug when the address uses a different slug', () => {
		expect(canonicalSlugFor('old-films', loaded)).toBe('my-films');
	});
	it('does nothing when the address is already the slug', () => {
		expect(canonicalSlugFor('my-films', loaded)).toBeNull();
	});
	it('does nothing before the collection has loaded', () => {
		expect(canonicalSlugFor('my-films', null)).toBeNull();
	});
});

describe('slugPatch', () => {
	it('sends nothing for an unchanged slug', () => {
		expect(slugPatch('my-films', 'my-films')).toEqual({});
		expect(slugPatch('my-films', '  my-films ')).toEqual({});
	});
	it('sends the new slug when it changed', () => {
		expect(slugPatch('my-films', 'films')).toEqual({ slug: 'films' });
	});
});

describe('slugSaveErrorMessage', () => {
	it('explains a taken slug', () => {
		expect(slugSaveErrorMessage(409, 'x')).toBe('That link is already used by another collection.');
	});
	it('uses the server message for a rejected slug', () => {
		expect(slugSaveErrorMessage(400, 'Slug cannot be empty')).toBe('Slug cannot be empty');
		expect(slugSaveErrorMessage(400, '')).toBe('That link is not valid.');
	});
	it('returns null for other statuses', () => {
		expect(slugSaveErrorMessage(500, 'x')).toBeNull();
	});
});

describe('collectionRouteParams', () => {
	it('links by slug, never by id', () => {
		expect(collectionRouteParams({ slug: 'my-films' })).toEqual({
			id: 'my-films'
		});
	});
});
