import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SettingResponse } from '../src/lib/api/client';

const { listMySettings, updateMySettings, resetMySetting, offline } = vi.hoisted(() => ({
	listMySettings: vi.fn(),
	updateMySettings: vi.fn(),
	resetMySetting: vi.fn(),
	offline: { offline: false }
}));
vi.mock('$lib/api/client', () => ({ listMySettings, updateMySettings, resetMySetting }));
vi.mock('$lib/offline.svelte', () => ({ offlineController: offline }));

import { OFFLINE_PREFERENCES, PreferencesController } from '../src/lib/preferences.svelte';
import { firstDayFor, regionFirstDay } from '../src/lib/calendar-settings';

const KEY = 'menagerist:preferences:';

function setting(over: Partial<SettingResponse>): SettingResponse {
	return {
		key: 'datetime.first_day',
		group: 'datetime',
		group_title: 'Dates and times',
		title: 'First day of the week',
		description: null,
		value: 'automatic',
		source: 'default',
		locked: false,
		env_name: 'MENAGERIST_DATETIME_FIRST_DAY',
		restart_required: false,
		stored_invalid: false,
		hidden: false,
		...over
	};
}

function memoryStorage(): Storage {
	const data = new Map<string, string>();
	return {
		get length() {
			return data.size;
		},
		key: (index: number) => [...data.keys()][index] ?? null,
		getItem: (key: string) => data.get(key) ?? null,
		setItem: (key: string, value: string) => void data.set(key, value),
		removeItem: (key: string) => void data.delete(key),
		clear: () => data.clear()
	};
}

beforeEach(() => {
	vi.resetAllMocks();
	vi.stubGlobal('localStorage', memoryStorage());
	offline.offline = false;
});

afterEach(() => vi.unstubAllGlobals());

describe('PreferencesController', () => {
	it('shows the kept copy at once, then the loaded values, and keeps them', async () => {
		localStorage.setItem(`${KEY}ann`, JSON.stringify([setting({ value: 'sunday' })]));
		let answer: (value: unknown) => void = () => {};
		listMySettings.mockReturnValue(new Promise((resolve) => (answer = resolve)));
		const prefs = new PreferencesController();

		const loading = prefs.load('ann');
		expect(prefs.value('datetime.first_day')).toBe('sunday');
		expect(prefs.loaded).toBe(false);

		answer({ data: [setting({ value: 'monday', source: 'user' })] });
		await loading;
		expect(prefs.value('datetime.first_day')).toBe('monday');
		expect(prefs.loaded).toBe(true);
		expect(JSON.parse(localStorage.getItem(`${KEY}ann`) ?? '[]')[0].value).toBe('monday');
	});

	it('keeps the copy when the load fails', async () => {
		localStorage.setItem(`${KEY}ann`, JSON.stringify([setting({ value: 'sunday' })]));
		listMySettings.mockRejectedValue(new TypeError('offline'));
		const prefs = new PreferencesController();

		await prefs.load('ann');

		expect(prefs.value('datetime.first_day')).toBe('sunday');
	});

	it("never shows one person's copy to another, and clears every copy", async () => {
		localStorage.setItem(`${KEY}ann`, JSON.stringify([setting({ value: 'sunday' })]));
		listMySettings.mockResolvedValue({ error: {} });
		const prefs = new PreferencesController();

		await prefs.load('bob');
		expect(prefs.value('datetime.first_day')).toBeUndefined();

		prefs.clear();
		expect(localStorage.getItem(`${KEY}ann`)).toBeNull();
	});

	it('saves a value and keeps the copy current', async () => {
		listMySettings.mockResolvedValue({ data: [setting({})] });
		updateMySettings.mockResolvedValue({
			data: [setting({ value: 'saturday', source: 'user' })]
		});
		const prefs = new PreferencesController();
		await prefs.load('ann');

		const outcome = await prefs.save('datetime.first_day', 'saturday');

		expect(outcome).toEqual({ ok: true });
		expect(updateMySettings).toHaveBeenCalledWith({
			body: { values: { 'datetime.first_day': 'saturday' } }
		});
		expect(prefs.value('datetime.first_day')).toBe('saturday');
		expect(localStorage.getItem(`${KEY}ann`)).toContain('saturday');
	});

	it('shows a change at once and puts it back when the server refuses it', async () => {
		listMySettings.mockResolvedValue({ data: [setting({ value: 'monday', source: 'user' })] });
		let answer: (value: unknown) => void = () => {};
		updateMySettings.mockReturnValue(new Promise((resolve) => (answer = resolve)));
		const prefs = new PreferencesController();
		await prefs.load('ann');

		const saving = prefs.save('datetime.first_day', 'sunday');
		expect(prefs.value('datetime.first_day')).toBe('sunday');

		answer({ error: {}, response: new Response(null, { status: 500 }) });
		expect((await saving).ok).toBe(false);
		expect(prefs.value('datetime.first_day')).toBe('monday');
	});

	it('resets to the default', async () => {
		listMySettings.mockResolvedValue({ data: [setting({ value: 'monday', source: 'user' })] });
		resetMySetting.mockResolvedValue({ data: setting({}) });
		const prefs = new PreferencesController();
		await prefs.load('ann');

		await prefs.reset('datetime.first_day');

		expect(resetMySetting).toHaveBeenCalledWith({ path: { key: 'datetime.first_day' } });
		expect(prefs.value('datetime.first_day')).toBe('automatic');
	});

	it('refuses a change offline, with the reason', async () => {
		offline.offline = true;
		const prefs = new PreferencesController();

		const outcome = await prefs.save('datetime.first_day', 'monday');

		expect(outcome).toEqual({ ok: false, message: OFFLINE_PREFERENCES });
		expect(updateMySettings).not.toHaveBeenCalled();
	});

	it("reports the server's reason for a refused value", async () => {
		updateMySettings.mockResolvedValue({
			error: { detail: 'Invalid value for datetime.first_day' },
			response: new Response(null, { status: 400 })
		});
		const prefs = new PreferencesController();

		const outcome = await prefs.save('datetime.first_day', 'friday');

		expect(outcome.ok).toBe(false);
	});
});

describe('first day of the week', () => {
	it('uses a fixed choice as given', () => {
		expect(firstDayFor('monday', 'en-US')).toBe(1);
		expect(firstDayFor('sunday', 'en-GB')).toBe(0);
		expect(firstDayFor('saturday', 'en-GB')).toBe(6);
	});

	it("follows the region's usual start when automatic", () => {
		expect(firstDayFor('automatic', 'en-GB')).toBe(regionFirstDay('en-GB'));
		expect(firstDayFor(undefined, 'en-US')).toBe(regionFirstDay('en-US'));
	});

	it('falls back to Monday for a locale it cannot read', () => {
		expect(regionFirstDay('not a locale!')).toBe(1);
	});
});
