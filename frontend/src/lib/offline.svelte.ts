import { answeredByProxy } from '$lib/proxy-answer';

/** How long to wait between checks while the server cannot be reached; the last one repeats. */
export const PROBE_DELAYS_MS = [2_000, 5_000, 10_000, 30_000];

/** Whether the app itself answers, through any proxy in front of it. */
async function reachServer(): Promise<boolean> {
	const response = await fetch('/api/health', { cache: 'no-store' });
	return response.ok && !answeredByProxy(response);
}

/**
 * Whether the app can reach its server: the browser's own online flag, plus whether the last
 * request got an answer (the flag stays true on a network with no route out). Pages that load on
 * mount read `retryCount` in their load effect, so Retry and coming back online reload them.
 */
/** What to say when the server cannot be reached, depending on whose side the problem is. */
export function unreachableWording(browserOffline: boolean): {
	title: string;
	detail: string;
	cantLoad: string;
} {
	return browserOffline
		? {
				title: "You're offline",
				detail: 'Check your connection, then try again.',
				cantLoad: "You're offline, so"
			}
		: {
				title: "Can't reach Menagerist",
				detail: "The server isn't answering. This page will load by itself when it's back.",
				cantLoad: "Can't reach Menagerist, so"
			};
}

export class OfflineController {
	private browserOnline = $state(true);
	private unreachable = $state(false);
	private probeTimer: ReturnType<typeof setTimeout> | undefined;
	private probeCount = 0;

	/** `probe` asks the server whether it is back; it may reject when it cannot be reached. */
	constructor(private readonly probe: () => Promise<boolean> = reachServer) {}
	/** Bumped each time pages should load again. */
	retryCount = $state(0);

	offline = $derived(!this.browserOnline || this.unreachable);
	/** The browser itself has no connection, rather than the server being away. */
	browserOffline = $derived(!this.browserOnline);

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

	/**
	 * A request failed before the server answered. Until one gets an answer, the server is checked
	 * in the background, so pages come back by themselves when a deployment or outage ends: the
	 * browser fires no `online` event for a server that was away while the network was fine.
	 */
	reportUnreachable(): void {
		this.unreachable = true;
		if (this.probeTimer === undefined) this.scheduleProbe();
	}

	/** The server answered, whatever the status. Reloads pages if it had been unreachable. */
	reportReachable(): void {
		this.stopProbing();
		if (!this.unreachable) return;
		this.unreachable = false;
		this.retry();
	}

	private scheduleProbe(): void {
		const delay = PROBE_DELAYS_MS[Math.min(this.probeCount, PROBE_DELAYS_MS.length - 1)];
		this.probeTimer = setTimeout(() => void this.runProbe(), delay);
	}

	private async runProbe(): Promise<void> {
		this.probeCount += 1;
		let back: boolean;
		try {
			back = await this.probe();
		} catch {
			back = false;
		}
		if (this.probeTimer === undefined) return; // An answer arrived meanwhile.
		if (back) this.reportReachable();
		else this.scheduleProbe();
	}

	private stopProbing(): void {
		clearTimeout(this.probeTimer);
		this.probeTimer = undefined;
		this.probeCount = 0;
	}

	/** Ask every page that loads on mount to load again. */
	retry(): void {
		this.retryCount += 1;
	}
}

export const offlineController = new OfflineController();
