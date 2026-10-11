import { errorMessage } from '$lib/api/errors';
import type { GraphPermission, IdentityPermission } from '$lib/api/generated/types.gen';

/** Every permission the backend can report. */
export type Permission = GraphPermission | IdentityPermission;

export const LOGIN_PATH = '/login';
export const SETUP_PATH = '/setup';
export const ACCOUNT_PATH = '/settings/account';
export const CSRF_COOKIE = 'menagerist_csrf';
export const CSRF_HEADER = 'X-CSRF-Token';

const PUBLIC_PATHS = [LOGIN_PATH, SETUP_PATH];
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export const isUnsafeMethod = (method: string): boolean => UNSAFE_METHODS.has(method.toUpperCase());

function normalisePath(pathname: string): string {
	return pathname.length > 1 ? pathname.replace(/\/+$/, '') || '/' : pathname;
}

export const isPublicPath = (pathname: string): boolean =>
	PUBLIC_PATHS.includes(normalisePath(pathname));

function hasUnsafeCharacters(value: string): boolean {
	for (const char of value) {
		const code = char.charCodeAt(0);
		if (char === '\\' || code < 0x20 || code === 0x7f) return true;
	}
	return false;
}

/**
 * Return `next` only when it is a same-origin path (open-redirect guard);
 * otherwise `/`. Rejects absolute and protocol-relative URLs, backslashes,
 * control characters and percent-encoded variants of those.
 */
export function safeNext(next: string | null | undefined): string {
	if (typeof next !== 'string' || next === '') return '/';

	const candidates = [next];
	let decoded = next;
	for (let round = 0; round < 3; round++) {
		let once: string;
		try {
			once = decodeURIComponent(decoded);
		} catch {
			return '/';
		}
		if (once === decoded) break;
		decoded = once;
		candidates.push(decoded);
	}

	for (const candidate of candidates) {
		if (!candidate.startsWith('/') || candidate.startsWith('//')) return '/';
		if (hasUnsafeCharacters(candidate)) return '/';
	}

	const origin = 'http://same-origin.invalid';
	try {
		if (new URL(next, origin).origin !== origin) return '/';
	} catch {
		return '/';
	}

	// Never send someone back to a sign-in or setup page.
	if (isPublicPath(next.split(/[?#]/)[0])) return '/';
	return next;
}

export interface GuardInput {
	pathname: string;
	search?: string;
	hash?: string;
	setupRequired: boolean;
	signedIn: boolean;
	passwordExpired: boolean;
	/** Keep the current page as `?next=` when sending someone to sign in. */
	rememberPath?: boolean;
}

export type GuardDecision = { action: 'allow' } | { action: 'redirect'; to: string };

/** Decide whether the current route may show, or where to send the visitor. */
export function guardDecision(input: GuardInput): GuardDecision {
	const path = normalisePath(input.pathname);
	const search = input.search ?? '';
	const allow: GuardDecision = { action: 'allow' };
	const go = (to: string): GuardDecision => ({ action: 'redirect', to });

	if (input.setupRequired) return path === SETUP_PATH ? allow : go(SETUP_PATH);

	if (!input.signedIn) {
		if (path === LOGIN_PATH) return allow;
		if (path === SETUP_PATH) return go(LOGIN_PATH);
		const here = path + search + (input.hash ?? '');
		return input.rememberPath !== false && here !== '/'
			? go(`${LOGIN_PATH}?next=${encodeURIComponent(here)}`)
			: go(LOGIN_PATH);
	}

	if (input.passwordExpired) return path === ACCOUNT_PATH ? allow : go(ACCOUNT_PATH);
	if (isPublicPath(path)) {
		return go(path === LOGIN_PATH ? safeNext(new URLSearchParams(search).get('next')) : '/');
	}
	return allow;
}

/** Read one cookie from a `document.cookie`-style string. */
export function readCookie(cookies: string, name: string): string | null {
	for (const part of cookies.split(';')) {
		const index = part.indexOf('=');
		if (index === -1 || part.slice(0, index).trim() !== name) continue;
		const raw = part.slice(index + 1).trim();
		try {
			return decodeURIComponent(raw);
		} catch {
			return raw;
		}
	}
	return null;
}

/** The CSRF token the server set for this browser, if any. */
export function csrfToken(): string | null {
	if (typeof document === 'undefined') return null;
	return readCookie(document.cookie, CSRF_COOKIE) || null;
}

/** The RFC 9457 `title` of a failed call, e.g. `PasswordUnchangedError`. */
export function problemTitle(error: unknown): string | null {
	if (error && typeof error === 'object' && 'title' in error) {
		const title = (error as { title: unknown }).title;
		if (typeof title === 'string') return title;
	}
	return null;
}

/** The RFC 9457 `type` of a failed call, e.g. `password_expired`. */
export function problemType(error: unknown): string | null {
	if (error && typeof error === 'object' && 'type' in error) {
		const type = (error as { type: unknown }).type;
		if (typeof type === 'string') return type;
	}
	return null;
}

/** Seconds from a `Retry-After` header, or null when it is missing or not a number. */
export function retryAfterSeconds(response: Response | null | undefined): number | null {
	const value = response?.headers.get('Retry-After');
	if (!value) return null;
	const seconds = Number(value);
	return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

export function throttleMessage(seconds: number | null): string {
	if (seconds === null) return 'Too many attempts. Wait a little while, then try again.';
	const minutes = Math.max(1, Math.ceil(seconds / 60));
	return `Too many attempts. Try again in ${minutes} ${minutes === 1 ? 'minute' : 'minutes'}.`;
}

export const ACCOUNT_DISABLED_MESSAGE = 'This account has been disabled. Ask an administrator.';

/** A plain-words message for a failed sign-in, setup or password call. */
export function authErrorMessage(result: { error?: unknown; response?: Response | null }): string {
	const { response } = result;
	if (!response) return 'You appear to be offline. Check your connection and try again.';
	if (response.status === 429) return throttleMessage(retryAfterSeconds(response));
	if (response.status === 403 && problemType(result.error) === 'account_disabled') {
		return ACCOUNT_DISABLED_MESSAGE;
	}
	if (response.status >= 500) return 'Something went wrong. Try again in a moment.';
	return errorMessage(result.error);
}

const CLAIM_WORDS: Record<string, [string, string]> = {
	items: ['item', 'items'],
	connections: ['connection', 'connections'],
	collections: ['collection', 'collections'],
	files: ['file', 'files'],
	examples: ['example pack', 'example packs']
};

/** Plain-words parts such as "3 items", leaving out kinds with nothing claimed. */
export function describeClaimed(claimed: Record<string, number>): string[] {
	return Object.entries(claimed)
		.filter(([, count]) => count > 0)
		.map(([kind, count]) => {
			const [one, many] = CLAIM_WORDS[kind] ?? [kind, kind];
			return `${count} ${count === 1 ? one : many}`;
		});
}

export const DISPLAY_NAME_MAX_LENGTH = 120;
export const DISPLAY_NAME_MESSAGE = `A display name must be 1 to ${DISPLAY_NAME_MAX_LENGTH} characters.`;

/** Why a display name cannot be saved, or null when it can. */
export function displayNameProblem(value: string): string | null {
	const length = value.trim().length;
	return length < 1 || length > DISPLAY_NAME_MAX_LENGTH ? DISPLAY_NAME_MESSAGE : null;
}

/** Whether a failed password change was refused because the new password matches the old. */
export function isPasswordUnchanged(error: unknown): boolean {
	return problemTitle(error) === 'PasswordUnchangedError';
}

export const PASSWORD_MIN_LENGTH = 10;
export const PASSWORD_MAX_LENGTH = 128;

/** A random password for an admin to hand over; ambiguous characters left out. */
export function generatePassword(length = 16): string {
	const alphabet = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
	const bytes = new Uint8Array(length);
	crypto.getRandomValues(bytes);
	return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join('');
}
