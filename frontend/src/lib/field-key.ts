const MAX_LENGTH = 40;

// Names inherited from Object.prototype would be found by `in` and index lookups on `properties`.
const RESERVED = new Set(Object.getOwnPropertyNames(Object.prototype));

type Keyed = { key: string; label: string; keyPending?: boolean };

/**
 * Derive a field key from its title: ASCII slug with underscores, capped at 40 characters,
 * `field` when nothing usable remains. Appends `_2`, `_3`, ... until it is unique
 * (case-insensitive) against `taken` and not a reserved object member name.
 */
export function generateFieldKey(title: string, taken: Iterable<string>): string {
	const base =
		title
			.normalize('NFKD')
			.replace(/[\u0080-\uffff]/g, '')
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '_')
			.replace(/^_+|_+$/g, '')
			.slice(0, MAX_LENGTH)
			.replace(/_+$/, '') || 'field';
	const used = new Set([...taken].map((k) => k.toLowerCase()));
	let key = base;
	for (let n = 2; used.has(key) || RESERVED.has(key); n++) key = `${base}_${n}`;
	return key;
}

/**
 * Give every `keyPending` item its final key, derived from its label and unique among the
 * settled keys and earlier pending items. Other items are returned unchanged, so a key
 * never changes once it has been saved.
 */
export function resolvePendingKeys<T extends Keyed>(items: T[]): T[] {
	const taken = new Set(items.filter((i) => !i.keyPending).map((i) => i.key));
	return items.map((item) => {
		if (!item.keyPending) return item;
		const key = generateFieldKey(item.label, taken);
		taken.add(key);
		return { ...item, key, keyPending: false };
	});
}
