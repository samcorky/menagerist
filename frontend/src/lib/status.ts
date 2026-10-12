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
