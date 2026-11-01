/** How a schedule is shown and typed: as a sentence, or as the cron expression itself. */
export type CronMode = 'words' | 'cron';

export const CRON_MODE_STORAGE_KEY = 'menagerist.cron-mode';
export const DEFAULT_CRON_MODE: CronMode = 'words';

/** Whatever was stored, or the default when it is missing or unrecognised. */
export function parseStoredMode(raw: string | null | undefined): CronMode {
	return raw === 'words' || raw === 'cron' ? raw : DEFAULT_CRON_MODE;
}

/** Read the saved mode; storage can be missing or blocked, and the page must still work. */
export function loadMode(storage: Pick<Storage, 'getItem'> | undefined): CronMode {
	try {
		return parseStoredMode(storage?.getItem(CRON_MODE_STORAGE_KEY));
	} catch {
		return DEFAULT_CRON_MODE;
	}
}

/** Remember the mode for next time; failing to is not an error. */
export function saveMode(storage: Pick<Storage, 'setItem'> | undefined, mode: CronMode): void {
	try {
		storage?.setItem(CRON_MODE_STORAGE_KEY, mode);
	} catch {
		// Private windows and blocked storage just forget the choice.
	}
}
