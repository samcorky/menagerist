/**
 * Whether the app can reach its server: the browser's own online flag, plus whether the last
 * request got an answer (the flag stays true on a network with no route out). Pages that load on
 * mount read `retryCount` in their load effect, so Retry and coming back online reload them.
 */
class OfflineController {
	private browserOnline = $state(true);
	private unreachable = $state(false);
	/** Bumped each time pages should load again. */
	retryCount = $state(0);

	offline = $derived(!this.browserOnline || this.unreachable);

	init(): () => void {
		if (typeof window === 'undefined') return () => {};
		this.browserOnline = navigator.onLine;
		const goOnline = () => {
			this.browserOnline = true;
			this.retry();
		};
		const goOffline = () => (this.browserOnline = false);
		window.addEventListener('online', goOnline);
		window.addEventListener('offline', goOffline);
		return () => {
			window.removeEventListener('online', goOnline);
			window.removeEventListener('offline', goOffline);
		};
	}

	/** A request failed before the server answered. */
	reportUnreachable(): void {
		this.unreachable = true;
	}

	/** The server answered, whatever the status. Reloads pages if it had been unreachable. */
	reportReachable(): void {
		if (!this.unreachable) return;
		this.unreachable = false;
		this.retry();
	}

	/** Ask every page that loads on mount to load again. */
	retry(): void {
		this.retryCount += 1;
	}
}

export const offlineController = new OfflineController();
