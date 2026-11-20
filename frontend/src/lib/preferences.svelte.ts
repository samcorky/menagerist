import {
	listMySettings,
	resetMySetting,
	updateMySettings,
	type SettingResponse
} from '$lib/api/client';
import { errorMessage, networkAwareError } from '$lib/api/errors';
import { offlineController } from '$lib/offline.svelte';

// The last settings loaded for each account, kept so the app behaves as the person set it up
// while the settings load, and when a later load fails. Keyed by account, and cleared when the
// session ends, so a shared browser never shows one person's choices to another.
const PREFIX = 'menagerist:preferences:';

/** Why a change cannot be made right now. */
export const OFFLINE_PREFERENCES = "You're offline, so your preferences can't be changed now.";

export type PreferenceOutcome = { ok: true } | { ok: false; message: string };

function readCopy(owner: string): SettingResponse[] | null {
	try {
		const parsed: unknown = JSON.parse(localStorage.getItem(PREFIX + owner) ?? 'null');
		return Array.isArray(parsed) ? (parsed as SettingResponse[]) : null;
	} catch {
		return null;
	}
}

function writeCopy(owner: string, items: readonly SettingResponse[]): void {
	try {
		localStorage.setItem(PREFIX + owner, JSON.stringify(items));
	} catch {
		// Storage is full or blocked: the copy is a convenience, so carry on without it.
	}
}

function removeCopies(): void {
	try {
		const keys: string[] = [];
		for (let i = 0; i < localStorage.length; i++) {
			const name = localStorage.key(i);
			if (name?.startsWith(PREFIX)) keys.push(name);
		}
		for (const name of keys) localStorage.removeItem(name);
	} catch {
		// Nothing to clear when storage is unavailable.
	}
}

/** The signed-in person's own settings: their values, sources and which are hidden. */
export class PreferencesController {
	items = $state.raw<SettingResponse[]>([]);
	/** True once values have come from the server this session, not only the kept copy. */
	loaded = $state(false);
	private owner: string | null = null;

	/** The effective value of a setting, or undefined before anything is known. */
	value(key: string): SettingResponse['value'] | undefined {
		return this.items.find((item) => item.key === key)?.value;
	}

	/** Show the kept copy at once, then load the current values; a failed load keeps the copy. */
	async load(owner: string): Promise<void> {
		if (this.owner !== owner) {
			this.owner = owner;
			this.items = readCopy(owner) ?? [];
			this.loaded = false;
		}
		try {
			const result = await listMySettings();
			if (this.owner !== owner || result.error || !result.data) return;
			this.items = result.data;
			writeCopy(owner, result.data);
			this.loaded = true;
		} catch {
			// Unreachable: keep what is shown.
		}
	}

	/** Forget the account's values and every kept copy; called as the session ends. */
	clear(): void {
		this.owner = null;
		this.items = [];
		this.loaded = false;
		removeCopies();
	}

	/** Save one value; the whole value replaces what was saved. */
	save(key: string, value: SettingResponse['value']): Promise<PreferenceOutcome> {
		return this.send(() => updateMySettings({ body: { values: { [key]: value } } }));
	}

	/** Go back to the default for one setting. */
	reset(key: string): Promise<PreferenceOutcome> {
		return this.send(() => resetMySetting({ path: { key } }));
	}

	private async send(
		call: () => Promise<{
			data?: SettingResponse | SettingResponse[];
			error?: unknown;
			response?: Response | null;
		}>
	): Promise<PreferenceOutcome> {
		if (offlineController.offline) return { ok: false, message: OFFLINE_PREFERENCES };
		try {
			const result = await call();
			if (result.error || !result.data) {
				const message =
					result.response?.status === 400
						? errorMessage(result.error)
						: networkAwareError(result).title;
				return { ok: false, message };
			}
			this.adopt(Array.isArray(result.data) ? result.data : [result.data]);
			return { ok: true };
		} catch {
			return { ok: false, message: OFFLINE_PREFERENCES };
		}
	}

	/** Take in values the server returned, keep the copy current. */
	private adopt(updated: readonly SettingResponse[]): void {
		const known = this.items.map((item) => item.key);
		this.items = [
			...this.items.map((item) => updated.find((u) => u.key === item.key) ?? item),
			...updated.filter((item) => !known.includes(item.key))
		];
		if (this.owner) writeCopy(this.owner, this.items);
	}
}

export const preferences = new PreferencesController();
