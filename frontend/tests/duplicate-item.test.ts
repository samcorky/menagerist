import { describe, expect, it } from 'vitest';
import {
	DEFAULT_DUPLICATE_CHOICES,
	defaultCopyName,
	duplicateBody
} from '../src/lib/duplicate-item';

describe('defaultCopyName', () => {
	it('prefixes the original name', () => {
		expect(defaultCopyName('Alien')).toBe('Copy of Alien');
	});
});

describe('duplicateBody', () => {
	it('copies only the collections by default', () => {
		expect(duplicateBody('Alien 2', DEFAULT_DUPLICATE_CHOICES)).toEqual({
			name: 'Alien 2',
			copy_relationships: false,
			copy_media: false,
			copy_cover: false,
			copy_collections: true
		});
	});

	it('maps each choice to its own flag', () => {
		expect(
			duplicateBody('Alien 2', {
				connections: true,
				media: false,
				cover: true,
				collections: false
			})
		).toEqual({
			name: 'Alien 2',
			copy_relationships: true,
			copy_media: false,
			copy_cover: true,
			copy_collections: false
		});
	});

	it('trims the name', () => {
		expect(duplicateBody('  Alien 2  ', DEFAULT_DUPLICATE_CHOICES).name).toBe('Alien 2');
	});
});
