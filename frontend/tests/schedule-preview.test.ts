import { describe, it, expect, vi } from 'vitest';
import {
	PREVIEW_TTL_MS,
	PreviewCache,
	formatRun,
	nextRuns,
	previewPlan,
	upcoming,
	type SchedulePreview
} from '../src/lib/schedule-preview';

const NOW = new Date('2026-10-28T12:00:00Z');

describe('formatRun', () => {
	it('shows the run in the instance zone in 24-hour time', () => {
		expect(formatRun('2026-10-29T03:00:00Z', 'UTC', NOW)).toBe('Thu 29 Oct, 03:00');
	});

	it('follows the clocks: the same 03:00 London is 02:00 UTC in summer', () => {
		expect(
			formatRun('2026-10-24T02:00:00Z', 'Europe/London', new Date('2026-10-23T12:00:00Z'))
		).toBe('Sat 24 Oct, 03:00');
		expect(
			formatRun('2026-10-25T03:00:00Z', 'Europe/London', new Date('2026-10-23T12:00:00Z'))
		).toBe('Sun 25 Oct, 03:00');
	});

	it('can land on a different day than UTC does', () => {
		expect(formatRun('2026-10-29T23:30:00Z', 'Asia/Tokyo', NOW)).toBe('Fri 30 Oct, 08:30');
	});

	it('adds the year only when it is not this year', () => {
		expect(formatRun('2027-01-04T09:00:00Z', 'UTC', NOW)).toBe('Mon 4 Jan 2027, 09:00');
	});
});

describe('nextRuns', () => {
	const preview: SchedulePreview = {
		timezone: 'UTC',
		runs: ['2026-10-29T03:00:00Z', '2026-10-30T03:00:00Z', '2026-10-31T03:00:00Z']
	};

	it('gives the next run and the ones after', () => {
		expect(nextRuns(preview, NOW)).toEqual({
			next: 'Thu 29 Oct, 03:00',
			later: ['Fri 30 Oct, 03:00', 'Sat 31 Oct, 03:00'],
			timezone: 'UTC'
		});
	});

	it('drops runs that have passed since the answer was fetched', () => {
		const later = new Date('2026-10-29T12:00:00Z');
		expect(upcoming(preview, later)).toEqual(['2026-10-30T03:00:00Z', '2026-10-31T03:00:00Z']);
		expect(nextRuns(preview, later)?.next).toBe('Fri 30 Oct, 03:00');
	});

	it('is null when nothing is due, as for a schedule that is off', () => {
		expect(nextRuns({ timezone: 'UTC', runs: [] }, NOW)).toBeNull();
		expect(nextRuns(preview, new Date('2026-12-01T00:00:00Z'))).toBeNull();
	});
});

describe('PreviewCache', () => {
	const answer: SchedulePreview = { timezone: 'UTC', runs: ['2026-10-29T03:00:00Z'] };

	it('asks once for the same expression, however it is spaced', async () => {
		const load = vi.fn().mockResolvedValue(answer);
		const cache = new PreviewCache(load, () => 0);
		await Promise.all([cache.get('0 3 * * *'), cache.get(' 0 3 * * * ')]);
		await cache.get('0 3 * * *');
		expect(load).toHaveBeenCalledTimes(1);
		expect(load).toHaveBeenCalledWith('0 3 * * *');
	});

	it('asks again after the answer has gone stale', async () => {
		let now = 0;
		const load = vi.fn().mockResolvedValue(answer);
		const cache = new PreviewCache(load, () => now);
		await cache.get('0 3 * * *');
		now = PREVIEW_TTL_MS + 1;
		await cache.get('0 3 * * *');
		expect(load).toHaveBeenCalledTimes(2);
	});

	it('does not keep a failure, so the next try can succeed', async () => {
		const load = vi.fn().mockResolvedValueOnce(new Error('offline')).mockResolvedValueOnce(answer);
		const cache = new PreviewCache(load, () => 0);
		expect(await cache.get('0 3 * * *')).toBeInstanceOf(Error);
		expect(await cache.get('0 3 * * *')).toEqual(answer);
	});

	it('turns a thrown error into an error value', async () => {
		const cache = new PreviewCache(vi.fn().mockRejectedValue(new Error('boom')), () => 0);
		expect(await cache.get('x')).toBeInstanceOf(Error);
		const odd = new PreviewCache(vi.fn().mockRejectedValue('nope'), () => 0);
		expect(await odd.get('x')).toBeInstanceOf(Error);
	});

	it('remembers that the preview is not available to this person', async () => {
		const load = vi.fn().mockResolvedValue('unavailable');
		const cache = new PreviewCache(load, () => 0);
		expect(await cache.get('0 3 * * *')).toBe('unavailable');
		await cache.get('0 3 * * *');
		expect(load).toHaveBeenCalledTimes(1);
	});
});

describe('previewPlan', () => {
	it('does not ask for an empty schedule, which is off', () => {
		expect(previewPlan('')).toBe('off');
		expect(previewPlan('   ')).toBe('off');
	});

	it('does not ask about a schedule the browser cannot read', () => {
		for (const bad of ['0 3 * *', '61 * * * *', '@daily', '0 3 ? * *']) {
			expect(previewPlan(bad), bad).toBe('skip');
		}
	});

	it('asks about one it can read', () => {
		expect(previewPlan('0 3 * * *')).toBe('fetch');
		expect(previewPlan(' */15 * * * * ')).toBe('fetch');
	});
});
