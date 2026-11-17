import { describe, expect, it } from 'vitest';
import {
	AVATAR_TONES,
	avatarPixels,
	avatarTone,
	avatarUrl,
	initialsFor,
	toneClasses
} from '../src/lib/avatars/avatar';

describe('initialsFor', () => {
	it('takes the first letter of the first two words', () => {
		expect(initialsFor('Alice Example')).toBe('AE');
		expect(initialsFor('Mary Jane Watson')).toBe('MJ');
	});

	it('takes one letter from a single word, ignoring spaces', () => {
		expect(initialsFor('  alice  ')).toBe('A');
		expect(initialsFor('Q')).toBe('Q');
	});

	it('keeps accents and upper-cases with the locale rules', () => {
		expect(initialsFor('Émile zola')).toBe('ÉZ');
	});

	it('does not split an emoji or a combined character', () => {
		expect(initialsFor('👩‍🚀 Sam')).toBe('👩‍🚀S');
	});

	it('falls back to a question mark for an empty name', () => {
		expect(initialsFor('')).toBe('?');
		expect(initialsFor('   ')).toBe('?');
	});
});

describe('avatarTone', () => {
	it('is stable for the same id', () => {
		const id = '01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e50';
		expect(avatarTone(id)).toBe(avatarTone(id));
	});

	it('stays within the palette and spreads across it', () => {
		const tones = new Set<number>();
		for (let i = 0; i < 200; i++) {
			const tone = avatarTone(`01978c3e-2b8b-7c3a-9c2e-${String(i).padStart(12, '0')}`);
			expect(tone).toBeGreaterThanOrEqual(0);
			expect(tone).toBeLessThan(AVATAR_TONES.length);
			tones.add(tone);
		}
		expect(tones.size).toBe(AVATAR_TONES.length);
	});

	it('maps every tone to classes for both themes', () => {
		for (const tone of AVATAR_TONES) {
			const classes = toneClasses(AVATAR_TONES.indexOf(tone));
			// -800 keeps small initials at AA (at least 4.5:1) on the light tint.
			expect(classes).toMatch(/ text-\w+-800 /);
			expect(classes).toMatch(/dark:text-\w+-300/);
		}
	});
});

describe('avatarUrl', () => {
	it('names the user, the size and the version', () => {
		expect(avatarUrl('u1', '0123456789abcdef', 128)).toBe(
			'/api/v1/users/u1/avatar/128?v=0123456789abcdef'
		);
	});

	it('encodes path and query parts', () => {
		expect(avatarUrl('a/b', 'x&y', 64)).toBe('/api/v1/users/a%2Fb/avatar/64?v=x%26y');
	});
});

describe('avatarPixels', () => {
	it('loads a stored size at least twice the shown size, for sharp screens', () => {
		expect(avatarPixels('sm')).toEqual({ shown: 24, load: 64 });
		expect(avatarPixels('md')).toEqual({ shown: 32, load: 64 });
		expect(avatarPixels('lg')).toEqual({ shown: 40, load: 128 });
		expect(avatarPixels('xl')).toEqual({ shown: 96, load: 256 });
	});
});
