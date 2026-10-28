import { describe, it, expect } from 'vitest';
import { explainCron } from '../src/lib/field-types/cron/explain';
import {
	CRON_MODE_STORAGE_KEY,
	loadMode,
	parseStoredMode,
	saveMode
} from '../src/lib/field-types/cron/cron-mode';
import {
	MINUTE_STEPS,
	SENTENCE_KINDS,
	buildCron,
	defaultSentence,
	formatTime,
	ordinal,
	parseCron,
	parseTime,
	switchKind,
	type Sentence
} from '../src/lib/field-types/cron/builder';

describe('explainCron', () => {
	it.each([
		['0 3 * * *', 'At 03:00'],
		['*/15 * * * *', 'Every 15 minutes'],
		['0 4 * * 1', 'At 04:00, only on Monday'],
		['30 2 1 * *', 'At 02:30, on day 1 of the month'],
		['0 9 * * 1-5', 'At 09:00, Monday through Friday']
	])('reads %s in 24-hour words', (expression, text) => {
		expect(explainCron(expression)).toEqual({ ok: true, text });
	});

	it('treats an empty schedule as off, as the server does', () => {
		expect(explainCron('')).toEqual({ ok: true, text: 'Never runs (off)' });
		expect(explainCron('   ')).toEqual({ ok: true, text: 'Never runs (off)' });
	});

	it('refuses a seconds part, which the scheduler does not run', () => {
		expect(explainCron('0 0 3 * * *').ok).toBe(false);
	});

	it('says why an expression cannot be read', () => {
		for (const bad of ['0 3 * *', '0 0 0 3 * * *', 'every day']) {
			const result = explainCron(bad);
			expect(result.ok, bad).toBe(false);
			if (!result.ok) expect(result.reason).toMatch(/^A schedule has five parts/);
		}
		const range = explainCron('61 * * * *');
		expect(range.ok).toBe(false);
		if (!range.ok) expect(range.reason).toMatch(/^Minutes part must be/);
	});
});

describe('buildCron', () => {
	it.each<[Sentence, string]>([
		[{ kind: 'off' }, ''],
		[{ kind: 'minutes', every: 15 }, '*/15 * * * *'],
		[{ kind: 'hourly', minute: 5 }, '5 * * * *'],
		[{ kind: 'daily', hour: 3, minute: 0 }, '0 3 * * *'],
		[{ kind: 'weekdays', hour: 9, minute: 30 }, '30 9 * * 1-5'],
		[{ kind: 'weekly', day: 0, hour: 4, minute: 0 }, '0 4 * * 0'],
		[{ kind: 'monthly', dayOfMonth: 28, hour: 23, minute: 59 }, '59 23 28 * *']
	])('%j is %j', (sentence, cron) => {
		expect(buildCron(sentence)).toBe(cron);
	});

	it('gives every kind a default that builds a schedule cronstrue can read', () => {
		for (const { kind } of SENTENCE_KINDS) {
			const cron = buildCron(defaultSentence(kind));
			expect(explainCron(cron).ok, kind).toBe(true);
		}
	});
});

describe('parseCron', () => {
	it('round-trips every sentence the builder can make', () => {
		const sentences: Sentence[] = [{ kind: 'off' }];
		for (const every of MINUTE_STEPS) sentences.push({ kind: 'minutes', every });
		for (let minute = 0; minute < 60; minute++) sentences.push({ kind: 'hourly', minute });
		for (const hour of [0, 3, 12, 23]) {
			for (const minute of [0, 5, 30, 59]) {
				sentences.push({ kind: 'daily', hour, minute });
				sentences.push({ kind: 'weekdays', hour, minute });
				for (let day = 0; day < 7; day++) sentences.push({ kind: 'weekly', day, hour, minute });
				for (const dayOfMonth of [1, 15, 28]) {
					sentences.push({ kind: 'monthly', dayOfMonth, hour, minute });
				}
			}
		}
		for (const sentence of sentences) {
			expect(parseCron(buildCron(sentence)), JSON.stringify(sentence)).toEqual(sentence);
		}
	});

	it('reads Sunday written as 7', () => {
		expect(parseCron('0 4 * * 7')).toEqual({ kind: 'weekly', day: 0, hour: 4, minute: 0 });
	});

	it('tolerates extra spaces', () => {
		expect(parseCron('  0   3 * *  * ')).toEqual({ kind: 'daily', hour: 3, minute: 0 });
	});

	it.each([
		'0 3 * * 1,3',
		'0 3 1 */2 *',
		'0 3 31 * *',
		'0 3 1 * 1',
		'*/7 * * * *',
		'*/15 3 * * *',
		'0 3,15 * * *',
		'0 3 * * MON',
		'60 3 * * *',
		'0 24 * * *',
		'0 0 3 * * *',
		'0 3 * *',
		'@daily',
		'nonsense'
	])('leaves %j as a custom schedule', (expression) => {
		expect(parseCron(expression)).toBeNull();
	});
});

describe('time inputs', () => {
	it('formats and parses HH:MM', () => {
		expect(formatTime(3, 5)).toBe('03:05');
		expect(parseTime('03:05')).toEqual({ hour: 3, minute: 5 });
		expect(parseTime('23:59')).toEqual({ hour: 23, minute: 59 });
	});

	it('rejects times that are not valid', () => {
		for (const bad of ['', '3:05', '24:00', '12:60', '12:5', 'ab:cd']) {
			expect(parseTime(bad), bad).toBeNull();
		}
	});
});

describe('ordinal', () => {
	it.each([
		[1, '1st'],
		[2, '2nd'],
		[3, '3rd'],
		[4, '4th'],
		[11, '11th'],
		[12, '12th'],
		[13, '13th'],
		[21, '21st'],
		[22, '22nd'],
		[23, '23rd'],
		[28, '28th']
	])('writes %i as %s', (n, text) => {
		expect(ordinal(n)).toBe(text);
	});
});

describe('remembered mode', () => {
	it('falls back to words for anything unrecognised', () => {
		expect(parseStoredMode(null)).toBe('words');
		expect(parseStoredMode(undefined)).toBe('words');
		expect(parseStoredMode('nonsense')).toBe('words');
		expect(parseStoredMode('cron')).toBe('cron');
		expect(parseStoredMode('words')).toBe('words');
	});

	it('round-trips through storage', () => {
		const data = new Map<string, string>();
		const storage = {
			getItem: (k: string) => data.get(k) ?? null,
			setItem: (k: string, v: string) => void data.set(k, v)
		};
		expect(loadMode(storage)).toBe('words');
		saveMode(storage, 'cron');
		expect(data.get(CRON_MODE_STORAGE_KEY)).toBe('cron');
		expect(loadMode(storage)).toBe('cron');
	});

	it('survives storage that is missing or throws', () => {
		const blocked = {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			}
		};
		expect(loadMode(undefined)).toBe('words');
		expect(loadMode(blocked)).toBe('words');
		expect(() => saveMode(blocked, 'cron')).not.toThrow();
		expect(() => saveMode(undefined, 'cron')).not.toThrow();
	});
});

describe('switchKind', () => {
	it('keeps the time of day when both kinds have one', () => {
		const weekly: Sentence = { kind: 'weekly', day: 3, hour: 9, minute: 30 };
		expect(switchKind(weekly, 'daily')).toEqual({ kind: 'daily', hour: 9, minute: 30 });
		expect(switchKind(weekly, 'monthly')).toEqual({
			kind: 'monthly',
			dayOfMonth: 1,
			hour: 9,
			minute: 30
		});
	});

	it('starts from the defaults when either kind has no time of day', () => {
		const daily: Sentence = { kind: 'daily', hour: 9, minute: 30 };
		expect(switchKind(daily, 'hourly')).toEqual(defaultSentence('hourly'));
		expect(switchKind(daily, 'off')).toEqual({ kind: 'off' });
		expect(switchKind({ kind: 'hourly', minute: 5 }, 'daily')).toEqual(defaultSentence('daily'));
	});

	it('starts from the defaults when there is no current sentence', () => {
		expect(switchKind(null, 'weekly')).toEqual(defaultSentence('weekly'));
	});
});
