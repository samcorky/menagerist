export type DurationStyle = 'clock' | 'words';

const CLOCK = /^(\d+):([0-5]?\d)(?::([0-5]?\d))?$/;
const WORDS = /^(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?$/i;

/**
 * Parse `3:45`, `1:02:03`, `1h 2m 3s` or a bare number of seconds into whole seconds.
 * With two clock parts the first is minutes (`75:30` is 75 minutes); with three it is hours.
 * Returns null when the text is not a duration.
 */
export function parseDuration(text: string): number | null {
	const t = text.trim();
	if (t === '') return null;
	if (/^\d+$/.test(t)) return Number(t);
	const clock = CLOCK.exec(t);
	if (clock) {
		const [, a, b, c] = clock;
		return c === undefined
			? Number(a) * 60 + Number(b)
			: Number(a) * 3600 + Number(b) * 60 + Number(c);
	}
	const words = WORDS.exec(t);
	if (words && (words[1] || words[2] || words[3])) {
		return Number(words[1] ?? 0) * 3600 + Number(words[2] ?? 0) * 60 + Number(words[3] ?? 0);
	}
	return null;
}

/** Format whole seconds as `3:45` / `1:02:03` (clock) or `1h 2m 3s` (words). */
export function formatDuration(seconds: number, style: DurationStyle = 'clock'): string {
	const total = Math.max(0, Math.round(seconds));
	const h = Math.floor(total / 3600);
	const m = Math.floor((total % 3600) / 60);
	const s = total % 60;
	if (style === 'words') {
		const parts = [h && `${h}h`, m && `${m}m`, s && `${s}s`].filter(Boolean);
		return parts.length > 0 ? parts.join(' ') : '0s';
	}
	const pad = (n: number) => String(n).padStart(2, '0');
	return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

/**
 * A value as a number of seconds, or null when it is not one. Forms hand widgets numbers as
 * digit strings, so `'225'` counts as 225.
 */
export function durationSeconds(value: unknown): number | null {
	const n = typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : value;
	return typeof n === 'number' && Number.isFinite(n) && n >= 0 ? n : null;
}
