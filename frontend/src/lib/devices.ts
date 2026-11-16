import Bowser from 'bowser';
import type { DisplayMode, OwnDeviceResponse } from '$lib/api/client';

export type DeviceKind = 'tool' | 'phone' | 'tablet' | 'desktop' | 'unknown';

export interface DeviceInfo {
	userAgent?: string | null;
	platform?: string | null;
	mobile?: boolean | null;
	/** How the app was shown when the session started; `standalone` is the installed app. */
	displayMode?: DisplayMode | null;
}

export interface DescribedDevice {
	label: string;
	kind: DeviceKind;
}

function detectTool(ua: string): string | null {
	const trimmed = ua.trim();
	if (/^curl(?:\/[\d.]+)?/i.test(trimmed)) return 'curl';
	if (/^python-requests(?:\/[\d.]+)?/i.test(trimmed)) return 'python-requests';
	if (/^wget(?:\/[\d.]+)?/i.test(trimmed)) return 'wget';
	if (/^httpie(?:\/[\d.]+)?/i.test(trimmed)) return 'HTTPie';
	if (/^postman(?:\/[\d.]+)?/i.test(trimmed)) return 'Postman';
	if (/^insomnia(?:\/[\d.]+)?/i.test(trimmed)) return 'Insomnia';
	return null;
}

/**
 * Derives a human-readable device label and icon category from the user agent and Client Hints.
 */
export function describeDevice(info: DeviceInfo): DescribedDevice {
	const ua = info.userAgent?.trim() || '';
	const platformHint = info.platform?.trim() || null;
	const mobileHint = info.mobile ?? null;

	const tool = ua ? detectTool(ua) : null;
	if (tool) {
		return { label: tool, kind: 'tool' };
	}

	let parsed: Bowser.Parser.ParsedResult | null = null;
	if (ua) {
		try {
			parsed = Bowser.parse(ua);
		} catch {
			parsed = null;
		}
	}

	let browser = parsed?.browser?.name?.trim() || null;
	if (browser === 'Samsung Internet for Android') {
		browser = 'Samsung Internet';
	}

	const os = parsed?.os?.name?.trim() || null;
	const system = platformHint || os || null;

	let kind: DeviceKind = 'unknown';
	if (
		mobileHint === true ||
		/iphone/i.test(ua) ||
		(/(android)/i.test(system || ua) && /mobile/i.test(ua))
	) {
		kind = 'phone';
	} else if (
		/ipad/i.test(ua) ||
		(/(android)/i.test(system || ua) && mobileHint === false && !/mobile/i.test(ua))
	) {
		kind = 'tablet';
	} else if (/(windows|macos|mac os|linux|chrome\s?os)/i.test(system || '')) {
		kind = 'desktop';
	}

	const where = system ? `on ${system}` : mobileHint === true ? 'on a phone' : null;
	const installed = info.displayMode === 'standalone';

	let label = 'Unknown device';
	if (installed) {
		// The installed app leads with "App" and names the browser engine behind it in brackets.
		label = [where ? `App ${where}` : 'App', browser ? `(${browser})` : null]
			.filter(Boolean)
			.join(' ');
	} else if (browser && where) {
		label = `${browser} ${where}`;
	} else if (browser) {
		label = browser;
	} else if (system) {
		label = `${system} device`;
	}

	return { label, kind };
}

/** What signing out one row of the devices list ends: a whole device, or one older session. */
export type DeviceRevoke = { kind: 'device'; id: string } | { kind: 'session'; id: string };

/**
 * What to show for a device: its name leads and the generated label sits beneath it; an unnamed
 * device shows the label alone.
 */
export function nameDevice(
	name: string | null | undefined,
	label: string
): { title: string; subtitle: string | null } {
	const trimmed = name?.trim();
	return trimmed ? { title: trimmed, subtitle: label } : { title: label, subtitle: null };
}

export interface DeviceRow extends DescribedDevice {
	key: string;
	/** The device's id, or `null` for a session from before devices, which cannot be named. */
	deviceId: string | null;
	name: string | null;
	title: string;
	subtitle: string | null;
	userAgent: string | null;
	address: string | null;
	firstSeen: string;
	lastSeen: string;
	current: boolean;
	sessionCount: number;
	revoke: DeviceRevoke;
}

/**
 * One row of the devices list. The newest session supplies the address and display mode; a
 * session from before devices were remembered has no device id and is signed out on its own.
 */
export function deviceRow(device: OwnDeviceResponse): DeviceRow {
	const latest = device.sessions[0];
	const described = describeDevice({
		userAgent: device.user_agent,
		platform: device.platform,
		mobile: device.mobile,
		displayMode: latest?.display_mode
	});
	return {
		...described,
		...nameDevice(device.name, described.label),
		key: device.id ?? `session-${latest?.id}`,
		deviceId: device.id ?? null,
		name: device.name ?? null,
		userAgent: device.user_agent ?? null,
		address: latest?.client_ip ?? null,
		firstSeen: device.first_seen_at,
		lastSeen: device.last_seen_at,
		current: device.current,
		sessionCount: device.sessions.length,
		revoke: device.id ? { kind: 'device', id: device.id } : { kind: 'session', id: latest.id }
	};
}

export { formatRelativeTime } from '$lib/format-date';
