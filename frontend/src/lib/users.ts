import { formatDateTime, formatRelativeTime } from '$lib/format-date';
import { displayNameProblem } from '$lib/auth';

/** Whether a sign-in lockout is still running at `now`. */
export function isLocked(lockedUntil: string | null | undefined, now: Date = new Date()): boolean {
	if (!lockedUntil) return false;
	const until = new Date(lockedUntil).getTime();
	return !isNaN(until) && until > now.getTime();
}

/** "Locked until 14:05", in the viewer's own time zone. */
export function lockedLabel(lockedUntil: string): string {
	const date = new Date(lockedUntil);
	if (isNaN(date.getTime())) return 'Locked';
	return `Locked until ${date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`;
}

/** "Never" or a relative time such as "3 hours ago"; `title` is the full local date. */
export function lastSignIn(
	value: string | null | undefined,
	now: Date = new Date()
): { text: string; title?: string } {
	if (!value) return { text: 'Never' };
	if (isNaN(new Date(value).getTime())) return { text: 'Never' };
	return { text: formatRelativeTime(value, now), title: formatDateTime(value).local };
}

/** Decide whether to keep, reject, or save a display name change. */
export function renameDecision(
	current: string,
	draft: string
): { kind: 'unchanged' } | { kind: 'problem'; message: string } | { kind: 'save'; name: string } {
	const name = draft.trim();
	if (name === current) return { kind: 'unchanged' };
	const message = displayNameProblem(name);
	return message ? { kind: 'problem', message } : { kind: 'save', name };
}
