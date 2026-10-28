import { describe, expect, it } from 'vitest';
import type { JobResponse } from '$lib/api/client';
import {
	isActive,
	nextRunLabel,
	runDuration,
	runStatusLabel,
	runTone,
	startedByHand
} from '$lib/scheduled-tasks';

const job = (over: Partial<JobResponse> = {}): JobResponse => ({
	job_key: 'backup.create',
	title: 'Back up everything',
	description: 'Saves a full copy.',
	lane: 'heavy',
	overlap: 'coalesce',
	missed_run: 'run_once',
	run_now_allowed: true,
	schedule: '0 3 * * *',
	next_run_at: '2026-10-29T03:00:00Z',
	active_run: null,
	...over
});

describe('run states', () => {
	it('labels every state in plain language', () => {
		expect(runStatusLabel('queued')).toBe('Waiting for a turn');
		expect(runStatusLabel('running')).toBe('Running');
		expect(runStatusLabel('succeeded')).toBe('Finished');
		expect(runStatusLabel('failed')).toBe("Didn't finish");
		expect(runStatusLabel('skipped')).toBe('Skipped');
		expect(runStatusLabel('abandoned')).toBe('Interrupted');
	});

	it('groups states by tone and activity', () => {
		expect(runTone('running')).toBe('working');
		expect(runTone('queued')).toBe('working');
		expect(runTone('succeeded')).toBe('good');
		expect(runTone('failed')).toBe('bad');
		expect(runTone('abandoned')).toBe('bad');
		expect(runTone('skipped')).toBe('neutral');
		expect(isActive('queued')).toBe(true);
		expect(isActive('running')).toBe(true);
		expect(isActive('succeeded')).toBe(false);
	});
});

describe('next run', () => {
	const format = (iso: string) => `at ${iso}`;

	it('formats a scheduled time', () => {
		expect(nextRunLabel(job(), format)).toBe('at 2026-10-29T03:00:00Z');
	});

	it('says when a task only runs by hand', () => {
		expect(nextRunLabel(job({ schedule: null, next_run_at: null }), format)).toBe(
			'Runs when you start it'
		);
	});

	it('says a switched-off or fixed task is not scheduled', () => {
		expect(
			nextRunLabel(job({ schedule: null, next_run_at: null, run_now_allowed: false }), format)
		).toBe('Not scheduled');
		expect(nextRunLabel(job({ next_run_at: null }), format)).toBe('Not scheduled');
	});
});

describe('run details', () => {
	it('shows durations compactly', () => {
		const at = (s: number) => new Date(Date.UTC(2026, 9, 28, 3, 0, s)).toISOString();
		expect(runDuration({ started_at: at(0), finished_at: at(8) })).toBe('8 s');
		expect(runDuration({ started_at: at(0), finished_at: at(68) })).toBe('1 min 8 s');
		expect(runDuration({ started_at: at(0), finished_at: at(120) })).toBe('2 min');
		expect(runDuration({ started_at: at(0), finished_at: at(3600 + 300) })).toBe('1 h 5 min');
		expect(runDuration({ started_at: at(0), finished_at: at(7200) })).toBe('2 h');
	});

	it('has no duration until the run has started and finished', () => {
		expect(runDuration({ started_at: null, finished_at: null })).toBeNull();
		expect(runDuration({ started_at: '2026-10-28T03:00:00Z', finished_at: null })).toBeNull();
	});

	it('knows a person started a run', () => {
		expect(startedByHand({ requested_by: 'u1' })).toBe(true);
		expect(startedByHand({ requested_by: null })).toBe(false);
	});
});
