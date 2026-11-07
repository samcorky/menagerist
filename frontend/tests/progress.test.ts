import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PhaseProgressResponse, ProgressSnapshotResponse } from '../src/lib/api/client';
import {
	currentPhase,
	headline,
	liveSnapshot,
	markLabel,
	percentOf,
	phaseCounts,
	phaseMark,
	phaseText,
	pollProgress,
	stoppedAt
} from '../src/lib/progress';

function phase(overrides: Partial<PhaseProgressResponse> = {}): PhaseProgressResponse {
	return {
		key: 'media',
		label: 'Restoring photos and files',
		state: 'running',
		done: 1240,
		total: 2000,
		unit: 'count',
		...overrides
	};
}

function snapshot(overrides: Partial<ProgressSnapshotResponse> = {}): ProgressSnapshotResponse {
	return {
		phases: [
			phase({ key: 'verify', label: 'Checking the backup', state: 'done', unit: 'bytes' }),
			phase()
		],
		message: null,
		percent: 62,
		outcome: 'running',
		...overrides
	};
}

describe('phase marks', () => {
	it.each([
		['done', 'done', 'Done'],
		['running', 'current', 'In progress'],
		['waiting', 'waiting', 'Waiting']
	] as const)('turns a %s phase into %s', (state, mark, label) => {
		expect(phaseMark({ state })).toBe(mark);
		expect(markLabel(mark)).toBe(label);
	});
});

describe('phase counts', () => {
	it('shows how many of how many for counted phases', () => {
		expect(phaseCounts(phase())).toBe('1,240 of 2,000');
		expect(phaseText(phase())).toBe('Restoring photos and files (1,240 of 2,000)');
	});

	it('shows no counts for bytes, which mean nothing to a person', () => {
		const bytes = phase({ unit: 'bytes', done: 5, total: 9 });
		expect(phaseCounts(bytes)).toBeNull();
		expect(phaseText(bytes)).toBe('Restoring photos and files');
	});

	it('shows no counts until the size is known', () => {
		expect(phaseCounts(phase({ total: null }))).toBeNull();
	});
});

describe('percent', () => {
	it.each([
		[62, 62],
		[61.6, 62],
		[-3, 0],
		[140, 100]
	])('keeps %s inside 0 to 100 as %s', (percent, expected) => {
		expect(percentOf({ percent })).toBe(expected);
	});
});

describe('headline', () => {
	it('uses the fallback before anything has been reported', () => {
		expect(headline(null, 'Receiving your backup')).toBe('Receiving your backup');
	});

	it('uses the fallback while no phase has started', () => {
		const waiting = snapshot({ phases: [phase({ state: 'waiting', done: 0, total: null })] });
		expect(headline(waiting, 'Receiving your backup')).toBe('Receiving your backup');
	});

	it('names the running phase', () => {
		expect(headline(snapshot(), 'x')).toBe('Restoring photos and files');
	});

	it('says when it has finished or what went wrong', () => {
		expect(headline(snapshot({ outcome: 'succeeded' }), 'x')).toBe('Finished');
		expect(headline(snapshot({ outcome: 'failed', message: 'The archive is damaged.' }), 'x')).toBe(
			'The archive is damaged.'
		);
		expect(headline(snapshot({ outcome: 'failed' }), 'x')).toBe("Didn't finish");
	});
});

describe('current phase and stopping point', () => {
	it('finds the running phase', () => {
		expect(currentPhase(snapshot())?.key).toBe('media');
		expect(currentPhase(snapshot({ phases: [] }))).toBeNull();
	});

	it('says where a run that did not finish stopped', () => {
		expect(stoppedAt(snapshot({ outcome: 'failed' }))).toBe(
			'Stopped while restoring photos and files'
		);
		expect(stoppedAt(snapshot({ outcome: 'failed', phases: [] }))).toBeNull();
		expect(stoppedAt(snapshot({ outcome: 'succeeded' }))).toBeNull();
	});
});

describe('live snapshots', () => {
	it('keeps only a snapshot of work that is still going', () => {
		expect(liveSnapshot(snapshot())).not.toBeNull();
		expect(liveSnapshot(snapshot({ outcome: 'succeeded' }))).toBeNull();
		expect(liveSnapshot(snapshot({ outcome: 'failed' }))).toBeNull();
		expect(liveSnapshot(null)).toBeNull();
	});
});

describe('polling', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => vi.useRealTimers());

	it('reads at once and then once per interval until stopped', async () => {
		const read = vi.fn(async () => snapshot());
		const seen: (ProgressSnapshotResponse | null)[] = [];
		const stop = pollProgress(read, (value) => seen.push(value), 1000);
		await vi.advanceTimersByTimeAsync(0);
		expect(read).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(2500);
		expect(read).toHaveBeenCalledTimes(3);
		stop();
		await vi.advanceTimersByTimeAsync(5000);
		expect(read).toHaveBeenCalledTimes(3);
		expect(seen).toHaveLength(3);
	});

	it('does not start another read while one is still waiting', async () => {
		let release: (value: ProgressSnapshotResponse | null) => void = () => {};
		const read = vi.fn(() => new Promise<ProgressSnapshotResponse | null>((r) => (release = r)));
		const stop = pollProgress(read, () => {}, 1000);
		await vi.advanceTimersByTimeAsync(5000);
		expect(read).toHaveBeenCalledTimes(1);
		release(null);
		await vi.advanceTimersByTimeAsync(1000);
		expect(read).toHaveBeenCalledTimes(2);
		stop();
	});

	it('skips a failed read and tries again', async () => {
		const read = vi
			.fn<() => Promise<ProgressSnapshotResponse | null>>()
			.mockRejectedValueOnce(new Error('offline'))
			.mockResolvedValue(snapshot());
		const seen: (ProgressSnapshotResponse | null)[] = [];
		const stop = pollProgress(read, (value) => seen.push(value), 1000);
		await vi.advanceTimersByTimeAsync(1000);
		expect(seen).toHaveLength(1);
		stop();
	});

	it('drops a read that finishes after it was stopped', async () => {
		let release: (value: ProgressSnapshotResponse | null) => void = () => {};
		const seen: (ProgressSnapshotResponse | null)[] = [];
		const stop = pollProgress(
			() => new Promise<ProgressSnapshotResponse | null>((r) => (release = r)),
			(value) => seen.push(value)
		);
		stop();
		release(snapshot());
		await vi.advanceTimersByTimeAsync(0);
		expect(seen).toEqual([]);
	});
});
