import { describe, expect, it } from 'vitest';
import {
	browserCheckOf,
	countStatuses,
	detailUnavailable,
	formatObservedValue,
	readinessOf,
	readyDetailOf,
	releaseViewOf,
	safeNotesUrl
} from '../src/lib/status';
import type { ReleaseResponse } from '../src/lib/api/client';
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

describe('detailUnavailable', () => {
	it('is true when the call threw or got no response', () => {
		expect(detailUnavailable(null)).toBe(true);
		expect(detailUnavailable({ error: undefined })).toBe(true);
	});

	it('is true for a 503 without a report', () => {
		expect(detailUnavailable({ error: { status: 503 }, response: res(503) })).toBe(true);
	});

	it('is false for a report, including a failing one', () => {
		const report = { status: 'fail', checks: {} };
		expect(detailUnavailable({ data: report, response: res(200) })).toBe(false);
		expect(detailUnavailable({ error: report, response: res(503) })).toBe(false);
	});

	it('is false for other refusals', () => {
		expect(detailUnavailable({ error: { detail: 'x' }, response: res(401) })).toBe(false);
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

describe('releaseViewOf', () => {
	const base: ReleaseResponse = { channel: 'stable', provider: 'github', status: 'unknown' };
	const newer: ReleaseResponse = {
		...base,
		status: 'update_available',
		latest_version: '0.2026.11.0',
		url: 'https://github.com/o/r/releases/tag/0.2026.11.0',
		published_at: '2026-11-01T12:00:00Z',
		checked_at: '2026-11-02T03:00:00Z',
		last_attempt_at: '2026-11-02T03:00:00Z'
	};

	it('calls out an available update and links the release notes', () => {
		const view = releaseViewOf(newer);
		expect(view.tone).toBe('attention');
		expect(view.badge).toBe('Update available');
		expect(view.summary).toContain('0.2026.11.0');
		expect(view.notesUrl).toBe(newer.url);
		expect(view.rows.map((row) => row.label)).toEqual([
			'Channel',
			'Latest release',
			'Published',
			'Last checked'
		]);
		expect(view.failureNote).toBeNull();
	});

	it('says up to date only when a check confirmed it', () => {
		expect(releaseViewOf({ ...newer, status: 'up_to_date' }).tone).toBe('ok');
		const never = releaseViewOf(base);
		expect(never.badge).toBe('Not checked yet');
		expect(never.tone).toBe('neutral');
		expect(never.notesUrl).toBeNull();
	});

	it('does not call a development build out of date', () => {
		const view = releaseViewOf({ ...newer, status: 'development' });
		expect(view.badge).toBe('Development build');
		expect(view.tone).toBe('neutral');
		expect(view.summary).toContain('cannot be compared');
	});

	it('describes a build that is ahead and a channel with no release', () => {
		expect(releaseViewOf({ ...newer, status: 'ahead' }).badge).toBe(
			'Newer than the latest release'
		);
		expect(releaseViewOf({ ...base, status: 'no_release' }).badge).toBe('No releases yet');
	});

	it('shows a failure beside the last good result, with the attempt time', () => {
		const view = releaseViewOf({
			...newer,
			last_attempt_at: '2026-11-03T03:00:00Z',
			failure: 'rate_limited'
		});
		expect(view.badge).toBe('Update available');
		expect(view.failureNote).toMatch(/limiting requests/);
		expect(view.rows.map((row) => row.label)).toContain('Last attempt');
	});

	it('reports a first check that failed as failed, not as unchecked', () => {
		const view = releaseViewOf({
			...base,
			last_attempt_at: '2026-11-03T03:00:00Z',
			failure: 'network'
		});
		expect(view.badge).toBe('Check failed');
		expect(view.failureNote).toBe('GitHub could not be reached.');
	});

	it('marks a prerelease and shows the channel in words', () => {
		const view = releaseViewOf({
			...newer,
			channel: 'preview',
			latest_version: '0.2026.12.0rc1',
			prerelease: true
		});
		expect(view.rows[0]).toEqual({ label: 'Channel', value: 'Preview' });
		expect(view.rows[1]?.value).toBe('0.2026.12.0rc1 (prerelease)');
	});
});

describe('safeNotesUrl', () => {
	it('allows only GitHub pages', () => {
		expect(safeNotesUrl('https://github.com/o/r/releases/tag/1')).toBe(
			'https://github.com/o/r/releases/tag/1'
		);
		expect(safeNotesUrl('https://evil.example/x')).toBeNull();
		expect(safeNotesUrl('javascript:alert(1)')).toBeNull();
		expect(safeNotesUrl('http://github.com/o/r')).toBeNull();
		expect(safeNotesUrl(null)).toBeNull();
		expect(safeNotesUrl(undefined)).toBeNull();
	});
});
