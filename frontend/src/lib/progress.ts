import type { PhaseProgressResponse, ProgressSnapshotResponse } from '$lib/api/client';

export type PhaseMark = 'done' | 'current' | 'waiting';

const counts = new Intl.NumberFormat('en-GB');

export function phaseMark(phase: Pick<PhaseProgressResponse, 'state'>): PhaseMark {
	if (phase.state === 'done') return 'done';
	return phase.state === 'running' ? 'current' : 'waiting';
}

/** Words for a phase's state, for people who cannot see the icon. */
export function markLabel(mark: PhaseMark): string {
	switch (mark) {
		case 'done':
			return 'Done';
		case 'current':
			return 'In progress';
		case 'waiting':
			return 'Waiting';
	}
}

/** The phase being worked on, if any. */
export function currentPhase(snapshot: ProgressSnapshotResponse): PhaseProgressResponse | null {
	return snapshot.phases.find((phase) => phase.state === 'running') ?? null;
}

/**
 * "1,240 of 2,000" for a phase counted in items; null for a byte phase (which
 * would mean nothing to a person) or one whose size is not known yet.
 */
export function phaseCounts(
	phase: Pick<PhaseProgressResponse, 'unit' | 'done' | 'total'>
): string | null {
	if (phase.unit !== 'count' || phase.total == null) return null;
	return `${counts.format(phase.done)} of ${counts.format(phase.total)}`;
}

/** A phase's label with its counts, such as "Restoring photos and files (1,240 of 2,000)". */
export function phaseText(phase: PhaseProgressResponse): string {
	const done = phaseCounts(phase);
	return done ? `${phase.label} (${done})` : phase.label;
}

/** The overall percentage as a whole number between 0 and 100. */
export function percentOf(snapshot: Pick<ProgressSnapshotResponse, 'percent'>): number {
	return Math.min(100, Math.max(0, Math.round(snapshot.percent)));
}

/**
 * One line saying what is happening. `fallback` covers the moment before any
 * phase has started, such as an upload that is still arriving.
 */
export function headline(snapshot: ProgressSnapshotResponse | null, fallback: string): string {
	if (!snapshot) return fallback;
	if (snapshot.outcome === 'succeeded') return 'Finished';
	if (snapshot.outcome === 'failed') return snapshot.message ?? "Didn't finish";
	const running = currentPhase(snapshot);
	return running ? running.label : fallback;
}

/** Where a run that did not finish had got to, such as "Stopped while Saving photos and files". */
export function stoppedAt(snapshot: ProgressSnapshotResponse): string | null {
	if (snapshot.outcome === 'succeeded') return null;
	const stopped = currentPhase(snapshot);
	return stopped ? `Stopped while ${stopped.label.toLowerCase()}` : null;
}

/**
 * A snapshot worth showing while the operation that reports it is still in
 * flight. A finished one belongs to an earlier run, because the request that
 * started this operation has not answered yet.
 */
export function liveSnapshot(
	snapshot: ProgressSnapshotResponse | null
): ProgressSnapshotResponse | null {
	return snapshot?.outcome === 'running' ? snapshot : null;
}

/**
 * Read progress repeatedly, one request at a time, until the returned function
 * is called. A failed read is skipped and tried again on the next beat.
 */
export function pollProgress(
	read: () => Promise<ProgressSnapshotResponse | null>,
	onSnapshot: (snapshot: ProgressSnapshotResponse | null) => void,
	intervalMs = 1000
): () => void {
	let stopped = false;
	let timer: ReturnType<typeof setTimeout> | undefined;

	async function beat() {
		if (stopped) return;
		try {
			const snapshot = await read();
			if (!stopped) onSnapshot(snapshot);
		} catch {
			// The next beat tries again.
		}
		if (!stopped) timer = setTimeout(beat, intervalMs);
	}

	void beat();
	return () => {
		stopped = true;
		clearTimeout(timer);
	};
}
