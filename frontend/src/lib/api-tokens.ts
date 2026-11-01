import { errorMessage } from '$lib/api/errors';
import { problemTitle, retryAfterSeconds, throttleMessage } from '$lib/auth';

/** An area of the app a token can be given access to, with the permissions behind it. */
export interface TokenArea {
	id: string;
	label: string;
	read: string[];
	write: string[];
}

/** Areas in display order. Backup permissions are not grantable, so they have no area. */
export const AREAS: TokenArea[] = [
	{ id: 'items', label: 'Items', read: ['graph:item:read'], write: ['graph:item:write'] },
	{
		id: 'item_types',
		label: 'Item types',
		read: ['graph:type:read'],
		write: ['graph:type:write']
	},
	{
		id: 'collections',
		label: 'Collections',
		read: ['collections:collection:read'],
		write: ['collections:collection:write']
	},
	{ id: 'media', label: 'Media', read: ['media:item:read'], write: ['media:item:write'] },
	{
		id: 'presets',
		label: 'Presets',
		read: ['presets:preset:read'],
		write: ['presets:preset:write']
	},
	{
		id: 'example_packs',
		label: 'Example packs',
		read: ['examples:pack:read'],
		write: ['examples:pack:install']
	}
];

export type TokenPreset = 'read' | 'readWrite';
export type AreaAccess = 'none' | 'read' | 'write';

/** Preset names for the simple view. */
export const TOKEN_PRESETS: Record<TokenPreset, string> = {
	read: 'Read only',
	readWrite: 'Read and write'
};

/** The grantable permissions a preset gives, in the grantable list's order. */
export function grantsForPreset(preset: TokenPreset, grantable: string[]): string[] {
	return preset === 'read' ? grantable.filter((p) => p.endsWith(':read')) : [...grantable];
}

/** The grantable permissions for the Advanced view's per-area choices; write includes read. */
export function grantsForSelection(
	selection: Record<string, AreaAccess>,
	grantable: string[]
): string[] {
	const wanted = new Set<string>();
	for (const area of AREAS) {
		const access = selection[area.id] ?? 'none';
		if (access === 'none') continue;
		area.read.forEach((p) => wanted.add(p));
		if (access === 'write') area.write.forEach((p) => wanted.add(p));
	}
	return AREAS.flatMap((a) => [...a.read, ...a.write]).filter(
		(p) => wanted.has(p) && grantable.includes(p)
	);
}

function joinWords(words: string[]): string {
	if (words.length < 2) return words.join('');
	return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

/** What a token can do, in words, e.g. "Read items and collections; write media". */
export function describeGrants(grants: string[]): string {
	const held = new Set(grants);
	const both: string[] = [];
	const readOnly: string[] = [];
	const writeOnly: string[] = [];
	for (const area of AREAS) {
		const canRead = area.read.some((p) => held.has(p));
		const canWrite = area.write.some((p) => held.has(p));
		const name = area.label.toLowerCase();
		if (canRead && canWrite) both.push(name);
		else if (canRead) readOnly.push(name);
		else if (canWrite) writeOnly.push(name);
	}
	const parts = [
		both.length ? `read and write ${joinWords(both)}` : '',
		readOnly.length ? `read ${joinWords(readOnly)}` : '',
		writeOnly.length ? `write ${joinWords(writeOnly)}` : ''
	].filter(Boolean);
	if (parts.length === 0) return 'No access';
	const text = parts.join('; ');
	return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Lifetimes a token can be given. */
export const EXPIRY_OPTIONS = [
	{ days: 30, label: '30 days' },
	{ days: 90, label: '90 days' },
	{ days: 365, label: '1 year' }
];
export const DEFAULT_EXPIRY_DAYS = 90;

const DAY_MS = 24 * 60 * 60 * 1000;
const SOON_DAYS = 14;

/** "Expires in 12 days", "Expires tomorrow", "Expires today" or "Expired". */
export function describeExpiry(expiresAt: string, now: Date): string {
	const remaining = new Date(expiresAt).getTime() - now.getTime();
	if (remaining <= 0) return 'Expired';
	if (remaining < DAY_MS) return 'Expires today';
	const days = Math.floor(remaining / DAY_MS);
	return days === 1 ? 'Expires tomorrow' : `Expires in ${days} days`;
}

/** True when the token expires within 14 days and has not expired yet. */
export function expiresSoon(expiresAt: string, now: Date): boolean {
	const remaining = new Date(expiresAt).getTime() - now.getTime();
	return remaining > 0 && remaining <= SOON_DAYS * DAY_MS;
}

function startOfDay(date: Date): number {
	return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** "Never used", "Used today", "Used yesterday" or "Used 3 days ago" by calendar day. */
export function describeLastUsed(lastUsedAt: string | null | undefined, now: Date): string {
	if (!lastUsedAt) return 'Never used';
	const days = Math.round((startOfDay(now) - startOfDay(new Date(lastUsedAt))) / DAY_MS);
	if (days <= 0) return 'Used today';
	return days === 1 ? 'Used yesterday' : `Used ${days} days ago`;
}

/** A plain sentence for a failed create, regenerate or revoke call. */
export function tokenErrorMessage(result: { error?: unknown; response?: Response | null }): string {
	const { response } = result;
	if (!response) return 'You appear to be offline. Check your connection and try again.';
	if (response.status === 429) return throttleMessage(retryAfterSeconds(response));
	if (response.status === 409) {
		return 'You have reached the limit of active tokens. Revoke one you no longer use, then try again.';
	}
	if (response.status === 400) {
		if (problemTitle(result.error) === 'CurrentPasswordIncorrectError') {
			return 'That password is not right.';
		}
		return `That request isn't valid. ${errorMessage(result.error)}`;
	}
	if (response.status === 404) return 'That token no longer exists. Reload the page.';
	if (response.status >= 500) return 'Something went wrong. Try again in a moment.';
	return errorMessage(result.error);
}

/** A curl command that lists what the token can do, for the one-time panel. */
export function sampleCurl(origin: string, token: string): string {
	return `curl -H "Authorization: Bearer ${token}" ${origin}/api/v1/auth/me/permissions`;
}
