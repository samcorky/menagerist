import { describe, expect, it } from 'vitest';
import type { JobResponse } from '$lib/api/client';
import {
	isActive,
	lastRunLabel,
	nextRunLabel,
	runDuration,
	runStatusLabel,
	runTone,
	scheduleLabel,
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
	confirm_required: false,
	schedule: '0 3 * * *',
	schedule_key: 'backup.schedule',
	next_run_at: '2026-10-29T03:00:00Z',
	active_run: null,
	last_run: null,
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

describe('schedule label', () => {
	const explain = (expression: string) =>
		expression === '0 3 * * *' ? 'Every day at 03:00' : null;

	it('puts a schedule in words, falling back to the expression itself', () => {
		expect(scheduleLabel(job(), explain)).toBe('Every day at 03:00');
		expect(scheduleLabel(job({ schedule: '5 4 * * 1' }), explain)).toBe('5 4 * * 1');
	});

	it('says Off for a schedulable task with none, and otherwise how it runs', () => {
		expect(scheduleLabel(job({ schedule: null }), explain)).toBe('Off');
		expect(scheduleLabel(job({ schedule: null, schedule_key: null }), explain)).toBe(
			'Only when started'
		);
		expect(
			scheduleLabel(job({ schedule: null, schedule_key: null, run_now_allowed: false }), explain)
		).toBe('Not scheduled');
	});
});

describe('last run label', () => {
	it('uses when it started, or when it was due if it never did', () => {
		const format = (iso: string) => `at ${iso}`;
		expect(lastRunLabel({ started_at: '2026-10-28T03:00:02Z', scheduled_for: 'x' }, format)).toBe(
			'at 2026-10-28T03:00:02Z'
		);
		expect(lastRunLabel({ started_at: null, scheduled_for: '2026-10-28T03:00:00Z' }, format)).toBe(
			'at 2026-10-28T03:00:00Z'
		);
	});
});
