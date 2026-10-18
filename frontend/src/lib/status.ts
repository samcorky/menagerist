import type { ReadyDetailResponse } from '$lib/api/client';

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
	}
	if (unit === 'flagged requests') {
		if (value === 0) return 'Nothing unusual in the last hour';
		return `${value} flagged ${value === 1 ? 'request' : 'requests'} in the last hour`;
	}
	return String(value);
}
