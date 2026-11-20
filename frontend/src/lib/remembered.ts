// Per-device interface preferences (open sections, sidebar state). Storage can be missing or
// blocked (private windows, site data off), so every access falls back instead of throwing.
const PREFIX = 'menagerist:';

export function readFlag(key: string, fallback: boolean): boolean {
	try {
		const stored = localStorage.getItem(PREFIX + key);
		return stored === null ? fallback : stored === '1';
	} catch {
		return fallback;
	}
}

export function writeFlag(key: string, value: boolean): void {
	try {
		localStorage.setItem(PREFIX + key, value ? '1' : '0');
	} catch {
		// Not remembering is harmless.
	}
}

/** Like `readFlag`, but `undefined` when nothing was stored, so a default can depend on context. */
export function readOptionalFlag(key: string): boolean | undefined {
	try {
		const stored = localStorage.getItem(PREFIX + key);
		return stored === null ? undefined : stored === '1';
	} catch {
		return undefined;
	}
}
