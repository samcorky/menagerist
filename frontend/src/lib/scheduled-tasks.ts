import type { JobResponse, JobRunResponse } from '$lib/api/client';

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

/** Whether the run was started by a person rather than the schedule. */
export function startedByHand(run: Pick<JobRunResponse, 'requested_by'>): boolean {
	return run.requested_by != null;
}
