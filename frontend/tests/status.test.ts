import { describe, expect, it } from 'vitest';
import { readinessOf, readyDetailOf } from '../src/lib/status';
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
