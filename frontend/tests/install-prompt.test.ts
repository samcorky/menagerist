import { beforeEach, describe, expect, it } from 'vitest';
import { installPrompt, manualInstall } from '../src/lib/install-prompt.svelte';
import { displayMode } from '../src/lib/display-mode.svelte';

const IPHONE_SAFARI =
	'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1';
const IPHONE_CHROME =
	'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/124.0.0.0 Mobile/15E148 Safari/604.1';
const MAC_SAFARI =
	'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15';
const MAC_CHROME =
	'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';
const ANDROID_CHROME =
	'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36';
const WINDOWS_EDGE =
	'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0';

describe('manualInstall', () => {
	it('says Safari on an iPhone installs through Share', () => {
		expect(manualInstall({ userAgent: IPHONE_SAFARI })).toBe('ios-safari');
	});

	it('says Safari on a Mac installs through the File menu', () => {
		expect(manualInstall({ userAgent: MAC_SAFARI, maxTouchPoints: 0 })).toBe('mac-safari');
	});

	it('treats an iPad that asks for a Mac page as iOS', () => {
		expect(manualInstall({ userAgent: MAC_SAFARI, maxTouchPoints: 5 })).toBe('ios-safari');
	});

	it.each([
		['Chrome on iOS', IPHONE_CHROME],
		['Chrome on a Mac', MAC_CHROME],
		['Chrome on Android', ANDROID_CHROME],
		['Edge on Windows', WINDOWS_EDGE],
		['nothing', '']
	])('offers no manual steps for %s', (_, userAgent) => {
		expect(manualInstall({ userAgent })).toBeNull();
	});
});

/** A window that records its listeners and lets a test fire the browser's install events. */
function fakeWindow(userAgent: string) {
	const listeners = new Map<string, (event: Event) => void>();
	const env = {
		navigator: { userAgent, maxTouchPoints: 0 },
		addEventListener: (type: string, listener: (event: Event) => void) =>
			listeners.set(type, listener),
		removeEventListener: (type: string) => listeners.delete(type)
	} as unknown as Window;
	return { env, listeners };
}

function installEvent(outcome: 'accepted' | 'dismissed') {
	let prevented = false;
	let shown = 0;
	const event = {
		preventDefault: () => (prevented = true),
		prompt: async () => {
			shown += 1;
		},
		userChoice: Promise.resolve({ outcome })
	};
	return { event: event as unknown as Event, prevented: () => prevented, shown: () => shown };
}

describe('installPrompt', () => {
	// One controller serves the whole app, so each test starts it from scratch.
	beforeEach(() => {
		installPrompt.event = null;
		installPrompt.choice = null;
	});

	it('keeps the browser event, shows it once on request and then lets go of it', async () => {
		const { env, listeners } = fakeWindow(WINDOWS_EDGE);
		const stop = installPrompt.init(env);
		expect(installPrompt.available).toBe(false);

		const fired = installEvent('accepted');
		listeners.get('beforeinstallprompt')!(fired.event);
		expect(fired.prevented()).toBe(true);
		expect(installPrompt.canPrompt).toBe(true);
		expect(installPrompt.available).toBe(true);

		expect(await installPrompt.prompt()).toBe('accepted');
		expect(fired.shown()).toBe(1);
		expect(installPrompt.canPrompt).toBe(false);
		expect(await installPrompt.prompt()).toBeNull();
		stop();
		expect(listeners.size).toBe(0);
	});

	it('says where the shown prompt stands, so a page never claims the browser cannot install', async () => {
		const { env, listeners } = fakeWindow(WINDOWS_EDGE);
		const stop = installPrompt.init(env);
		expect(installPrompt.choice).toBeNull();

		listeners.get('beforeinstallprompt')!(installEvent('dismissed').event);
		const shown = installPrompt.prompt();
		// While the browser's dialog is open the event is already spent.
		expect(installPrompt.canPrompt).toBe(false);
		expect(installPrompt.choice).toBe('waiting');
		await shown;
		expect(installPrompt.choice).toBe('dismissed');

		// The browser offers the app again later, and the button comes back.
		listeners.get('beforeinstallprompt')!(installEvent('accepted').event);
		expect(installPrompt.choice).toBeNull();
		expect(installPrompt.canPrompt).toBe(true);
		stop();
	});

	it('forgets the event once the app is installed', () => {
		const { env, listeners } = fakeWindow(WINDOWS_EDGE);
		const stop = installPrompt.init(env);
		listeners.get('beforeinstallprompt')!(installEvent('accepted').event);
		listeners.get('appinstalled')!(new Event('appinstalled'));
		expect(installPrompt.canPrompt).toBe(false);
		expect(installPrompt.choice).toBe('accepted');
		stop();
	});

	it('offers the manual steps on Safari with no event, and nothing once installed', () => {
		const { env } = fakeWindow(IPHONE_SAFARI);
		const stop = installPrompt.init(env);
		expect(installPrompt.manual).toBe('ios-safari');
		expect(installPrompt.available).toBe(true);

		displayMode.standalone = true;
		try {
			expect(installPrompt.available).toBe(false);
		} finally {
			displayMode.standalone = false;
		}
		stop();
	});
});
