import type { JobResponse, JobRunResponse } from '$lib/api/client';
import { currentPhase, phaseText, stoppedAt } from '$lib/progress';

export type RunStatus = JobRunResponse['status'];

export function runStatusLabel(status: RunStatus): string {
	switch (status) {
		case 'queued':
			return 'Waiting for a turn';
		case 'running':
			return 'Running';
		case 'succeeded':
			return 'Finished';
		case 'failed':
			return "Didn't finish";
		case 'skipped':
			return 'Skipped';
		case 'abandoned':
			return 'Interrupted';
	}
}

export type RunTone = 'working' | 'good' | 'bad' | 'neutral';

export function runTone(status: RunStatus): RunTone {
	if (status === 'queued' || status === 'running') return 'working';
	if (status === 'succeeded') return 'good';
	if (status === 'failed' || status === 'abandoned') return 'bad';
	return 'neutral';
}

/** Whether a run is still waiting for, or being handled by, the worker. */
export function isActive(status: RunStatus): boolean {
	return status === 'queued' || status === 'running';
}

/** When a task next runs, in words; "Not scheduled" when it only runs by hand. */
export function nextRunLabel(job: JobResponse, format: (iso: string) => string): string {
	if (!job.schedule) return job.run_now_allowed ? 'Runs when you start it' : 'Not scheduled';
	return job.next_run_at ? format(job.next_run_at) : 'Not scheduled';
}

/** How long a finished run took, such as "1 min 8 s"; null until it has both ends. */
export function runDuration(
	run: Pick<JobRunResponse, 'started_at' | 'finished_at'>
): string | null {
	if (!run.started_at || !run.finished_at) return null;
	const seconds = Math.max(
		0,
		Math.round((Date.parse(run.finished_at) - Date.parse(run.started_at)) / 1000)
	);
	if (seconds < 60) return `${seconds} s`;
	const minutes = Math.floor(seconds / 60);
	const rest = seconds % 60;
	if (minutes < 60) return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
	const hours = Math.floor(minutes / 60);
	return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
}

/**
 * What a run's progress says, in words: the phase a running job is in (with
 * counts), or where one that did not finish stopped. Null when it has nothing
 * to add, such as a run that finished or never reported.
 */
export function runProgressText(run: Pick<JobRunResponse, 'status' | 'progress'>): string | null {
	const progress = run.progress;
	if (!progress) return null;
	if (run.status === 'running') {
		const phase = currentPhase(progress);
		return phase ? phaseText(phase) : null;
	}
	return run.status === 'failed' || run.status === 'abandoned' ? stoppedAt(progress) : null;
}

/** Whether the run was started by a person rather than the schedule. */
export function startedByHand(run: Pick<JobRunResponse, 'requested_by'>): boolean {
	return run.requested_by != null;
}

/** A task's schedule in words: "Off" when it can be scheduled but is not, "Only when started" otherwise. */
export function scheduleLabel(
	job: Pick<JobResponse, 'schedule' | 'schedule_key' | 'run_now_allowed'>,
	explain: (expression: string) => string | null
): string {
	if (job.schedule) return explain(job.schedule) ?? job.schedule;
	if (job.schedule_key) return 'Off';
	return job.run_now_allowed ? 'Only when started' : 'Not scheduled';
}

/** When a run last happened, using the moment it started and falling back to when it was due. */
export function lastRunLabel(
	run: Pick<JobRunResponse, 'started_at' | 'scheduled_for'>,
	format: (iso: string) => string
): string {
	return format(run.started_at ?? run.scheduled_for);
}

const JOB_ID_PREFIX = 'job-';

/** The element id of a scheduled task's row, which a link's `#` fragment points at. */
export function jobId(jobKey: string): string {
	return `${JOB_ID_PREFIX}${jobKey}`;
}

/** The task a URL fragment (`#job-<key>`) points at, or null for any other fragment. */
export function jobKeyFromHash(hash: string): string | null {
	const id = hash.startsWith('#') ? hash.slice(1) : hash;
	if (!id.startsWith(JOB_ID_PREFIX) || id.length === JOB_ID_PREFIX.length) return null;
	try {
		return decodeURIComponent(id.slice(JOB_ID_PREFIX.length));
	} catch {
		return null;
	}
}
