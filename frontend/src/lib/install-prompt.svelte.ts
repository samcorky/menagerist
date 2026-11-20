/**
 * Whether, and how, this browser can install the app. Chromium browsers fire `beforeinstallprompt`:
 * the event is kept so an Install button can show the browser's own prompt. Safari never fires it,
 * so on iOS and macOS Safari people are shown the manual steps instead. Installed already (a
 * standalone window) there is nothing to offer.
 */

import { displayMode } from '$lib/display-mode.svelte';

/** Where the app can only be installed by hand, and which steps apply there. */
export type ManualInstall = 'ios-safari' | 'mac-safari';

/** The parts of `navigator` the platform is read from, so tests can pass their own. */
export interface InstallEnvironment {
	userAgent: string;
	/** Above 1 on an iPad, which asks for a Mac's page. */
	maxTouchPoints?: number;
}

/** The non-standard event Chromium browsers fire when the app can be installed. */
export interface BeforeInstallPromptEvent extends Event {
	prompt(): Promise<void>;
	userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

// Other browsers on iOS and Mac carry "Safari" in their user agent too; each names itself.
const NOT_SAFARI = /CriOS|FxiOS|EdgiOS|OPiOS|Chrome|Chromium|Edg\/|OPR\/|Firefox|Android/;

/** Where the app is installed by hand (Safari on iOS or macOS), or `null` where it is not. */
export function manualInstall(env: InstallEnvironment): ManualInstall | null {
	const ua = env.userAgent;
	if (!/Safari/.test(ua) || NOT_SAFARI.test(ua)) return null;
	if (/iPhone|iPad|iPod/.test(ua)) return 'ios-safari';
	if (/Macintosh/.test(ua)) return (env.maxTouchPoints ?? 0) > 1 ? 'ios-safari' : 'mac-safari';
	return null;
}

/** What happened to the browser's install prompt once it was shown. */
export type InstallChoice = 'waiting' | 'accepted' | 'dismissed';

class InstallPromptController {
	/** The kept `beforeinstallprompt` event; `null` until one fires and again once it is used. */
	event = $state<BeforeInstallPromptEvent | null>(null);
	manual = $state<ManualInstall | null>(null);
	/**
	 * Where the shown prompt stands, so a page does not claim the browser cannot install the app
	 * while the browser's own dialog is open, or after it was closed. `null` until one is shown.
	 */
	choice = $state<InstallChoice | null>(null);

	canPrompt = $derived(this.event !== null);
	/** Something can be offered: the native prompt or the manual steps, and not installed yet. */
	available = $derived(!displayMode.standalone && (this.canPrompt || this.manual !== null));

	/** Listen for the browser's install events; returns the cleanup. */
	init(env: Window | undefined = typeof window === 'undefined' ? undefined : window): () => void {
		if (env === undefined) return () => {};
		this.manual = manualInstall({
			userAgent: env.navigator.userAgent,
			maxTouchPoints: env.navigator.maxTouchPoints
		});
		const onPrompt = (event: Event) => {
			// Hold the browser's own mini prompt back; the Install button shows it instead.
			event.preventDefault();
			this.event = event as BeforeInstallPromptEvent;
			// The browser offers the app again, as it does in time after a closed prompt.
			this.choice = null;
		};
		const onInstalled = () => {
			this.event = null;
			this.choice = 'accepted';
		};
		env.addEventListener('beforeinstallprompt', onPrompt);
		env.addEventListener('appinstalled', onInstalled);
		return () => {
			env.removeEventListener('beforeinstallprompt', onPrompt);
			env.removeEventListener('appinstalled', onInstalled);
		};
	}

	/** Show the browser's install prompt; the kept event can be used once. */
	async prompt(): Promise<'accepted' | 'dismissed' | null> {
		const event = this.event;
		if (!event) return null;
		this.event = null;
		this.choice = 'waiting';
		await event.prompt();
		const { outcome } = await event.userChoice;
		this.choice = outcome;
		return outcome;
	}
}

export const installPrompt = new InstallPromptController();
