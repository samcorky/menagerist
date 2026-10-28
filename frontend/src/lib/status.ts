import type { BrowserCheckResponse, ReadyDetailResponse } from '$lib/api/client';

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
