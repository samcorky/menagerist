/**
 * Account pictures: the initials-on-colour default and the address of an uploaded
 * picture. The server stores each picture at 64, 128 and 256 pixels under a version
 * that changes with it, so a picture's address can be cached for good.
 */

import { TYPE_COLOUR_KEYS, type TypeColour } from '$lib/type-appearance';

export type AvatarSize = 'sm' | 'md' | 'lg' | 'xl';
type StoredSize = 64 | 128 | 256;

/** The item-type palette, minus grey, so every person gets a colour. */
export const AVATAR_TONES = TYPE_COLOUR_KEYS.filter(
	(key): key is Exclude<TypeColour, 'gray'> => key !== 'gray'
);

// Whole class names, so Tailwind finds them. The -800/-300 text is darker than the
// item-type chips, so small initials still read at AA contrast in both themes.
const TONE_CLASSES: Record<(typeof AVATAR_TONES)[number], string> = {
	red: 'bg-red-500/15 text-red-800 dark:text-red-300',
	orange: 'bg-orange-500/15 text-orange-800 dark:text-orange-300',
	amber: 'bg-amber-500/15 text-amber-800 dark:text-amber-300',
	green: 'bg-green-500/15 text-green-800 dark:text-green-300',
	teal: 'bg-teal-500/15 text-teal-800 dark:text-teal-300',
	blue: 'bg-blue-500/15 text-blue-800 dark:text-blue-300',
	violet: 'bg-violet-500/15 text-violet-800 dark:text-violet-300',
	pink: 'bg-pink-500/15 text-pink-800 dark:text-pink-300'
};

const PIXELS: Record<AvatarSize, { shown: number; load: StoredSize }> = {
	sm: { shown: 24, load: 64 },
	md: { shown: 32, load: 64 },
	lg: { shown: 40, load: 128 },
	xl: { shown: 96, load: 256 }
};

const graphemes = new Intl.Segmenter(undefined, { granularity: 'grapheme' });

function firstGrapheme(word: string): string {
	return graphemes.segment(word)[Symbol.iterator]().next().value?.segment ?? '';
}

/** The first letter of each of the first two words of a name. */
export function initialsFor(displayName: string): string {
	const words = displayName.trim().split(/\s+/u).filter(Boolean);
	if (words.length === 0) return '?';
	return words
		.slice(0, 2)
		.map((word) => firstGrapheme(word))
		.join('')
		.toLocaleUpperCase();
}

/** A stable palette index for an account (FNV-1a over its id). */
export function avatarTone(userId: string): number {
	let hash = 0x811c9dc5;
	for (let i = 0; i < userId.length; i++) {
		hash ^= userId.charCodeAt(i);
		hash = Math.imul(hash, 0x01000193) >>> 0;
	}
	return hash % AVATAR_TONES.length;
}

/** Background and text classes for a tone index. */
export function toneClasses(tone: number): string {
	return TONE_CLASSES[AVATAR_TONES[tone] ?? AVATAR_TONES[0]];
}

/** The size drawn on screen, and the stored size loaded for it (twice, for sharp screens). */
export function avatarPixels(size: AvatarSize): { shown: number; load: StoredSize } {
	return PIXELS[size];
}

/** Where one stored size of an account's current picture is served. */
export function avatarUrl(userId: string, version: string, size: StoredSize): string {
	return `/api/v1/users/${encodeURIComponent(userId)}/avatar/${size}?v=${encodeURIComponent(version)}`;
}
