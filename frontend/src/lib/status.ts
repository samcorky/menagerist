import type { BrowserCheckResponse, ReadyDetailResponse, ReleaseResponse } from '$lib/api/client';

export type Readiness = 'pass' | 'fail';

interface CallResult {
	data?: unknown;
	error?: unknown;
	response?: Response | null;
}

const isObject = (value: unknown): value is Record<string, unknown> =>
	typeof value === 'object' && value !== null;

/** The overall state from `/health/ready`; a 503 means fail. Null when the answer is unusable. */
export function readinessOf(result: CallResult): Readiness | null {
	for (const body of [result.data, result.error]) {
		if (isObject(body) && (body.status === 'pass' || body.status === 'fail')) return body.status;
	}
	return result.response?.status === 503 ? 'fail' : null;
}

/** The per-check report; a failing report arrives as a 503 carrying the same body. */
export function readyDetailOf(result: CallResult): ReadyDetailResponse | null {
	for (const body of [result.data, result.error]) {
		if (isObject(body) && isObject(body.checks) && typeof body.status === 'string') {
			return body as unknown as ReadyDetailResponse;
		}
	}
	return null;
}

/**
 * Whether a detail call failed because the service cannot serve signed-in requests (a 503
 * without a report, or no answer at all); null stands for a call that threw.
 */
export function detailUnavailable(result: CallResult | null): boolean {
	if (result === null) return true;
	if (readyDetailOf(result) !== null) return false;
	return !result.response || result.response.status === 503;
}

export interface StatusCounts {
	total: number;
	pass: number;
	warn: number;
	fail: number;
}

/** Tallies observations by status; unknown statuses count towards the total only. */
export function countStatuses(observations: ReadonlyArray<{ status: string }>): StatusCounts {
	const counts: StatusCounts = { total: observations.length, pass: 0, warn: 0, fail: 0 };
	for (const { status } of observations) {
		if (status === 'pass' || status === 'warn' || status === 'fail') counts[status] += 1;
	}
	return counts;
}

/** Renders an observed value with its unit. */
export function formatObservedValue(value: unknown, unit: string | null | undefined): string {
	// A check that could not run reports the word `unknown` in its own unit.
	if (value === 'unknown') return 'Unknown';
	if (unit === 'percent') return `${value}%`;
	if (unit === 'ms') return `${value} ms`;
	if (unit === 'GiB' && typeof value === 'number' && Number.isFinite(value)) {
		return `${value.toFixed(2)} GiB`;
	}
	if (unit === 'state' && typeof value === 'string') {
		if (value === 'not-writable') return 'Not writable';
		if (value === 'missing') return 'Missing';
		if (value === 'writable') return 'Writable';
		if (value === 'running') return 'Running';
		if (value === 'stale') return 'No recent heartbeat';
		if (value === 'unknown') return 'Unknown';
	}
	if (unit === 'open origins') return value === 0 ? 'Listed origins only' : 'Any origin allowed';
	if (unit === 'flagged requests') {
		if (value === 0) return 'Nothing unusual in the last hour';
		return `${value} flagged ${value === 1 ? 'request' : 'requests'} in the last hour`;
	}
	return String(value);
}

export type BrowserCheck =
	| {
			state: 'pass' | 'warn' | 'fail';
			output: string | null;
			origin: string | null;
			seenOrigin: string;
	  }
	| { state: 'stripped' }
	| { state: 'unavailable' };

/**
 * What the browser check found. A `403` of type `csrf_failed` means the headers were removed on
 * the way in (the caller is a browser); any other failure says nothing about the headers.
 */
export function browserCheckOf(result: CallResult): BrowserCheck {
	const body = result.data;
	if (isObject(body) && typeof body.seen_origin === 'string') {
		const { status, output, origin } = body as unknown as BrowserCheckResponse;
		return {
			state: status,
			output: output ?? null,
			origin: origin ?? null,
			seenOrigin: body.seen_origin
		};
	}
	const error = result.error;
	const refusedAsCsrf =
		result.response?.status === 403 &&
		isObject(error) &&
		typeof error.type === 'string' &&
		error.type.endsWith('csrf_failed');
	return refusedAsCsrf ? { state: 'stripped' } : { state: 'unavailable' };
}

export type ReleaseTone = 'ok' | 'attention' | 'neutral';

export interface ReleaseView {
	tone: ReleaseTone;
	badge: string;
	summary: string;
	rows: Array<{ label: string; value: string; time?: boolean }>;
	/** The release notes, only when the link is a GitHub page. */
	notesUrl: string | null;
	/** Why the last attempt failed, in words, or null. */
	failureNote: string | null;
}

const CHANNEL_LABELS = { stable: 'Stable', preview: 'Preview' } as const;

const FAILURE_NOTES: Record<NonNullable<ReleaseResponse['failure']>, string> = {
	network: 'GitHub could not be reached.',
	timeout: 'GitHub took too long to answer.',
	rate_limited: 'GitHub is limiting requests right now. Try again later.',
	not_found: 'The repository or its releases could not be found.',
	bad_response: 'GitHub gave an answer that could not be read.'
};

/** A release link is shown only when it points at GitHub, never at an arbitrary address. */
export function safeNotesUrl(url: string | null | undefined): string | null {
	return typeof url === 'string' && url.startsWith('https://github.com/') ? url : null;
}

/**
 * How the Status page describes the last release check. An uncheckable build is never
 * reported as up to date, and a failed attempt keeps showing the last good answer.
 */
export function releaseViewOf(release: ReleaseResponse): ReleaseView {
	const latest = release.latest_version ?? null;
	const channel = CHANNEL_LABELS[release.channel];
	const failureNote = release.failure ? FAILURE_NOTES[release.failure] : null;

	let tone: ReleaseTone = 'neutral';
	let badge: string;
	let summary: string;
	switch (release.status) {
		case 'update_available':
			tone = 'attention';
			badge = 'Update available';
			summary = `Version ${latest} is available.`;
			break;
		case 'up_to_date':
			tone = 'ok';
			badge = 'Up to date';
			summary = `This is the latest ${channel.toLowerCase()} release.`;
			break;
		case 'ahead':
			badge = 'Newer than the latest release';
			summary = `This build is newer than the latest ${channel.toLowerCase()} release, ${latest}.`;
			break;
		case 'development':
			badge = 'Development build';
			summary = `This is a development build, so it cannot be compared with releases. The latest ${channel.toLowerCase()} release is ${latest}.`;
			break;
		case 'no_release':
			badge = 'No releases yet';
			summary = `No ${channel.toLowerCase()} release has been published.`;
			break;
		default:
			badge = failureNote ? 'Check failed' : 'Not checked yet';
			summary = failureNote
				? 'The last check did not finish, so nothing is known about newer releases.'
				: 'Choose Check now to look for a newer release.';
	}

	const rows: ReleaseView['rows'] = [{ label: 'Channel', value: channel }];
	if (latest) {
		rows.push({
			label: 'Latest release',
			value: release.prerelease ? `${latest} (prerelease)` : latest
		});
	}
	if (release.published_at) {
		rows.push({ label: 'Published', value: release.published_at, time: true });
	}
	if (release.checked_at) {
		rows.push({ label: 'Last checked', value: release.checked_at, time: true });
	}
	if (failureNote && release.last_attempt_at) {
		rows.push({ label: 'Last attempt', value: release.last_attempt_at, time: true });
	}

	return { tone, badge, summary, rows, notesUrl: safeNotesUrl(release.url), failureNote };
}
