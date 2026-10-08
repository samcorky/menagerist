import { describe, expect, it } from 'vitest';
import {
	MAX_COLLECTION_NAME_LENGTH,
	addItemsErrorMessage,
	collectionSaveErrorMessage,
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
