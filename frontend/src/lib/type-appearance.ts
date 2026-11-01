import { TYPE_ICONS, TYPE_ICON_WORDS, type TypeIconName } from '$lib/type-icons';

/** The palette an item type can use; the same list the server accepts (a shared contract test checks). */
export const TYPE_COLOUR_KEYS = [
	'gray',
	'red',
	'orange',
	'amber',
	'green',
	'teal',
	'blue',
	'violet',
	'pink'
] as const;
export type TypeColour = (typeof TYPE_COLOUR_KEYS)[number];

type ColourClasses = { text: string; background: string; swatch: string };

// Whole class names, so Tailwind finds them; each reads well on light and dark backgrounds.
const COLOURS: Record<TypeColour, ColourClasses> = {
	gray: {
		text: 'text-neutral-600 dark:text-neutral-400',
		background: 'bg-neutral-500/10',
		swatch: 'bg-neutral-500'
	},
	red: {
		text: 'text-red-600 dark:text-red-400',
		background: 'bg-red-500/10',
		swatch: 'bg-red-500'
	},
	orange: {
		text: 'text-orange-600 dark:text-orange-400',
		background: 'bg-orange-500/10',
		swatch: 'bg-orange-500'
	},
	amber: {
		text: 'text-amber-600 dark:text-amber-400',
		background: 'bg-amber-500/10',
		swatch: 'bg-amber-500'
	},
	green: {
		text: 'text-green-600 dark:text-green-400',
		background: 'bg-green-500/10',
		swatch: 'bg-green-500'
	},
	teal: {
		text: 'text-teal-600 dark:text-teal-400',
		background: 'bg-teal-500/10',
		swatch: 'bg-teal-500'
	},
	blue: {
		text: 'text-blue-600 dark:text-blue-400',
		background: 'bg-blue-500/10',
		swatch: 'bg-blue-500'
	},
	violet: {
		text: 'text-violet-600 dark:text-violet-400',
		background: 'bg-violet-500/10',
		swatch: 'bg-violet-500'
	},
	pink: {
		text: 'text-pink-600 dark:text-pink-400',
		background: 'bg-pink-500/10',
		swatch: 'bg-pink-500'
	}
};

/** Classes for a type colour; none, or a name this version does not know, is the neutral grey. */
export function colourClasses(colour: string | null | undefined): ColourClasses {
	return COLOURS[(colour ?? 'gray') as TypeColour] ?? COLOURS.gray;
}

const ICON_NAMES = Object.keys(TYPE_ICONS) as TypeIconName[];

export function isKnownIcon(name: string | null | undefined): name is TypeIconName {
	return name != null && Object.hasOwn(TYPE_ICONS, name);
}

/**
 * Icons whose name, or whose search words, start with every word typed. Name matches come first;
 * a blank search lists every icon.
 */
export function searchIcons(query: string): TypeIconName[] {
	const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
	if (tokens.length === 0) return [...ICON_NAMES];
	const startsAny = (words: string[], token: string) => words.some((w) => w.startsWith(token));
	const byName: TypeIconName[] = [];
	const byWords: TypeIconName[] = [];
	for (const name of ICON_NAMES) {
		const nameWords = name.split('-');
		const extra = TYPE_ICON_WORDS[name].split(' ');
		if (tokens.every((t) => startsAny(nameWords, t))) byName.push(name);
		else if (tokens.every((t) => startsAny(nameWords, t) || startsAny(extra, t)))
			byWords.push(name);
	}
	return [...byName, ...byWords];
}

function pick<T>(list: readonly T[], rng: () => number, avoid?: T | null): T {
	let index = Math.min(list.length - 1, Math.floor(rng() * list.length));
	if (avoid != null && list[index] === avoid) index = (index + 1) % list.length;
	return list[index];
}

/** A random icon from the available set, never `avoid` (the current choice). */
export function randomIcon(rng: () => number = Math.random, avoid?: string | null): TypeIconName {
	return pick(ICON_NAMES, rng, avoid as TypeIconName | null | undefined);
}

export function randomColour(rng: () => number = Math.random, avoid?: string | null): TypeColour {
	return pick(TYPE_COLOUR_KEYS, rng, avoid as TypeColour | null | undefined);
}
