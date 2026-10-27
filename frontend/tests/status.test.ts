import { describe, expect, it } from 'vitest';
import {
	browserCheckOf,
	countStatuses,
	formatObservedValue,
	readinessOf,
	readyDetailOf
} from '../src/lib/status';
import { FILE_TOO_LARGE_MESSAGE, uploadErrorMessage } from '../src/lib/api/errors';

const res = (status: number) => new Response(null, { status });

describe('readinessOf', () => {
	it('reads pass from a 200', () => {
		expect(readinessOf({ data: { status: 'pass' }, response: res(200) })).toBe('pass');
	});

	it('treats a 503 body as the fail state', () => {
		expect(readinessOf({ error: { status: 'fail' }, response: res(503) })).toBe('fail');
		expect(readinessOf({ error: undefined, response: res(503) })).toBe('fail');
	});

	it('returns null for an unusable answer', () => {
		expect(readinessOf({ error: { detail: 'x' }, response: res(500) })).toBeNull();
		expect(readinessOf({ data: {}, response: res(200) })).toBeNull();
	});
});

describe('readyDetailOf', () => {
	const report = { status: 'fail', checks: { 'database:ping': [] } };

	it('accepts the report from a 200 or a 503', () => {
		expect(readyDetailOf({ data: report })).toBe(report);
		expect(readyDetailOf({ error: report })).toBe(report);
	});

	it('ignores a problem body', () => {
		expect(readyDetailOf({ error: { detail: 'Forbidden' } })).toBeNull();
	});
});

describe('countStatuses', () => {
	it('counts each status and the total', () => {
		const counts = countStatuses([
			{ status: 'pass' },
			{ status: 'pass' },
			{ status: 'warn' },
			{ status: 'fail' }
		]);
		expect(counts).toEqual({ total: 4, pass: 2, warn: 1, fail: 1 });
	});

	it('keeps the parts adding up to the total for known statuses', () => {
		const counts = countStatuses([{ status: 'warn' }, { status: 'warn' }]);
		expect(counts.pass + counts.warn + counts.fail).toBe(counts.total);
	});

	it('counts an unknown status in the total only', () => {
		expect(countStatuses([{ status: 'odd' }])).toEqual({ total: 1, pass: 0, warn: 0, fail: 0 });
	});

	it('handles no observations', () => {
		expect(countStatuses([])).toEqual({ total: 0, pass: 0, warn: 0, fail: 0 });
	});
});

describe('formatObservedValue', () => {
	it('appends the unit', () => {
		expect(formatObservedValue(42, 'percent')).toBe('42%');
		expect(formatObservedValue(12, 'ms')).toBe('12 ms');
		expect(formatObservedValue(41.7, 'GiB')).toBe('41.70 GiB');
	});

	it('presents storage states in plain language', () => {
		expect(formatObservedValue('writable', 'state')).toBe('Writable');
		expect(formatObservedValue('not-writable', 'state')).toBe('Not writable');
		expect(formatObservedValue('missing', 'state')).toBe('Missing');
	});

	it('presents worker heartbeat states in plain language', () => {
		expect(formatObservedValue('running', 'state')).toBe('Running');
		expect(formatObservedValue('stale', 'state')).toBe('No recent heartbeat');
		expect(formatObservedValue('unknown', 'state')).toBe('Unknown');
	});

	it('says nothing unusual rather than zero when no request was flagged', () => {
		expect(formatObservedValue(0, 'flagged requests')).toBe('Nothing unusual in the last hour');
	});

	it('counts flagged requests, singular for one', () => {
		expect(formatObservedValue(3, 'flagged requests')).toBe('3 flagged requests in the last hour');
		expect(formatObservedValue(1, 'flagged requests')).toBe('1 flagged request in the last hour');
	});

	it('prints a bare value for other units', () => {
		expect(formatObservedValue(7, undefined)).toBe('7');
		expect(formatObservedValue('ok', 'other')).toBe('ok');
	});
});

describe('uploadErrorMessage', () => {
	it('names a too-large file on 413', () => {
		expect(uploadErrorMessage({ error: '', response: res(413) })).toBe(FILE_TOO_LARGE_MESSAGE);
	});

	it('shows the server detail for other failures', () => {
		expect(
			uploadErrorMessage({ error: { detail: 'Image is too large.' }, response: res(400) })
		).toBe('Image is too large.');
	});

	it('says offline without a response', () => {
		expect(uploadErrorMessage({ error: undefined, response: undefined })).toMatch(/offline/);
	});
});

describe('browserCheckOf', () => {
	const body = {
		status: 'warn',
		sec_fetch_site: 'same-origin',
		origin: 'https://public.example',
		seen_origin: 'http://10.0.0.5:8000',
		output: 'check the proxy'
	};

	it('reads the report from a 200', () => {
		expect(browserCheckOf({ data: body, response: res(200) })).toEqual({
			state: 'warn',
			output: 'check the proxy',
			origin: 'https://public.example',
			seenOrigin: 'http://10.0.0.5:8000'
		});
	});

	it('fills the optional fields with null', () => {
		const { output, origin, ...rest } = body;
		void output;
		void origin;
		expect(browserCheckOf({ data: { ...rest, status: 'pass' }, response: res(200) })).toEqual({
			state: 'pass',
			output: null,
			origin: null,
			seenOrigin: 'http://10.0.0.5:8000'
		});
	});

	it('reads a csrf_failed 403 as removed headers', () => {
		const error = { type: 'https://menagerist.example/problems/csrf_failed' };
		expect(browserCheckOf({ error, response: res(403) })).toEqual({ state: 'stripped' });
	});

	it('does not blame the headers for a permission 403, other errors or no answer', () => {
		const permission = { type: 'https://menagerist.example/problems/forbidden' };
		expect(browserCheckOf({ error: permission, response: res(403) })).toEqual({
			state: 'unavailable'
		});
		expect(browserCheckOf({ error: { type: 'csrf_failed' }, response: res(500) })).toEqual({
			state: 'unavailable'
		});
		expect(browserCheckOf({ error: undefined, response: null })).toEqual({ state: 'unavailable' });
	});
});

describe('formatObservedValue for CORS', () => {
	it('reads the open-origins flag as words', () => {
		expect(formatObservedValue(0, 'open origins')).toBe('Listed origins only');
		expect(formatObservedValue(1, 'open origins')).toBe('Any origin allowed');
	});
});
