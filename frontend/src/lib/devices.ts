import Bowser from 'bowser';

export type DeviceKind = 'tool' | 'phone' | 'tablet' | 'desktop' | 'unknown';

export interface DeviceInfo {
	userAgent?: string | null;
	platform?: string | null;
	mobile?: boolean | null;
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

	let label = 'Unknown device';
	if (browser && system) {
		label = `${browser} on ${system}`;
	} else if (browser && mobileHint === true) {
		label = `${browser} on a phone`;
	} else if (browser) {
		label = browser;
	} else if (system) {
		label = `${system} device`;
	}

	return { label, kind };
}

export { formatRelativeTime } from '$lib/format-date';
