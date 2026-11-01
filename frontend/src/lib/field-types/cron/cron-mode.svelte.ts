import { loadMode, saveMode, type CronMode } from './cron-mode';

const storage = () => (typeof localStorage === 'undefined' ? undefined : localStorage);

class CronModeController {
	value = $state<CronMode>(loadMode(storage()));

	set(mode: CronMode): void {
		this.value = mode;
		saveMode(storage(), mode);
	}
}

export const cronMode = new CronModeController();
