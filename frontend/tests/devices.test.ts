import { describe, it, expect } from 'vitest';
import { describeDevice, deviceRow, nameDevice } from '../src/lib/devices';
import type { OwnDeviceResponse, SessionResponse } from '../src/lib/api/client';

describe('describeDevice', () => {
	it('labels Firefox on Linux', () => {
		const result = describeDevice({
			userAgent: 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0'
		});
		expect(result).toEqual({
			label: 'Firefox on Linux',
			kind: 'desktop'
		});
	});

	it('labels Chrome on Windows without hints', () => {
		const result = describeDevice({
			userAgent:
				'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
		});
		expect(result).toEqual({
			label: 'Chrome on Windows',
			kind: 'desktop'
		});
	});

	it('labels Chrome on Windows with hints', () => {
		const result = describeDevice({
			userAgent:
				'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
			platform: 'Windows',
			mobile: false
		});
		expect(result).toEqual({
			label: 'Chrome on Windows',
			kind: 'desktop'
		});
	});

	it('labels Microsoft Edge on Windows', () => {
		const result = describeDevice({
			userAgent:
				'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
			platform: 'Windows',
			mobile: false
		});
		expect(result).toEqual({
			label: 'Microsoft Edge on Windows',
			kind: 'desktop'
		});
	});

	it('labels Safari on macOS', () => {
		const result = describeDevice({
			userAgent:
				'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
		});
		expect(result).toEqual({
			label: 'Safari on macOS',
			kind: 'desktop'
		});
	});

	it('labels Safari on iPhone', () => {
		const result = describeDevice({
			userAgent:
				'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1'
		});
		expect(result).toEqual({
			label: 'Safari on iOS',
			kind: 'phone'
		});
	});

	it('labels Chrome on Android', () => {
		const result = describeDevice({
			userAgent:
				'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
			platform: 'Android',
			mobile: true
		});
		expect(result).toEqual({
			label: 'Chrome on Android',
			kind: 'phone'
		});
	});

	it('labels Samsung Internet on Android', () => {
		const result = describeDevice({
			userAgent:
				'Mozilla/5.0 (Linux; Android 13; SAMSUNG SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.0.0 Mobile Safari/537.36',
			platform: 'Android',
			mobile: true
		});
		expect(result).toEqual({
			label: 'Samsung Internet on Android',
			kind: 'phone'
		});
	});

	it('labels curl and identifies as tool', () => {
		const result = describeDevice({
			userAgent: 'curl/8.4.0'
		});
		expect(result).toEqual({
			label: 'curl',
			kind: 'tool'
		});
	});

	it('labels python-requests and identifies as tool', () => {
		const result = describeDevice({
			userAgent: 'python-requests/2.31.0'
		});
		expect(result).toEqual({
			label: 'python-requests',
			kind: 'tool'
		});
	});

	it('handles null, empty, and junk user agents', () => {
		expect(describeDevice({ userAgent: null })).toEqual({
			label: 'Unknown device',
			kind: 'unknown'
		});
		expect(describeDevice({ userAgent: '' })).toEqual({
			label: 'Unknown device',
			kind: 'unknown'
		});
		expect(describeDevice({ userAgent: 'some random junk 123' })).toEqual({
			label: 'Unknown device',
			kind: 'unknown'
		});
	});

	it('labels real Windows desktop capture', () => {
		const result = describeDevice({
			userAgent:
				'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36',
			platform: 'Windows',
			mobile: false
		});
		expect(result).toEqual({
			label: 'Chrome on Windows',
			kind: 'desktop'
		});
	});

	it('labels real reduced Android capture', () => {
		const result = describeDevice({
			userAgent:
				'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36',
			platform: 'Android',
			mobile: true
		});
		expect(result).toEqual({
			label: 'Chrome on Android',
			kind: 'phone'
		});
	});

	it('labels iPad as tablet', () => {
		const result = describeDevice({
			userAgent:
				'Mozilla/5.0 (iPad; CPU OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1'
		});
		expect(result).toEqual({
			label: 'Safari on iOS',
			kind: 'tablet'
		});
	});

	it('labels Android tablet as tablet', () => {
		const result = describeDevice({
			userAgent:
				'Mozilla/5.0 (Linux; Android 12; SM-X800) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36',
			platform: 'Android',
			mobile: false
		});
		expect(result).toEqual({
			label: 'Chrome on Android',
			kind: 'tablet'
		});
	});

	it('labels browser on phone when mobile hint is true without OS', () => {
		const result = describeDevice({
			userAgent: 'Mozilla/5.0 Chrome/120.0.0.0',
			mobile: true
		});
		expect(result).toEqual({
			label: 'Chrome on a phone',
			kind: 'phone'
		});
	});
});

describe('describeDevice and the display mode', () => {
	const iphone =
		'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';

	it('leads with App for a standalone session', () => {
		const result = describeDevice({ userAgent: iphone, displayMode: 'standalone' });
		expect(result.label).toBe('App on iOS (Safari)');
		expect(result.kind).toBe('phone');
	});

	it('names the platform from Client Hints for the installed app', () => {
		const android =
			'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Mobile Safari/537.36';
		const result = describeDevice({
			userAgent: android,
			platform: 'Android',
			mobile: true,
			displayMode: 'standalone'
		});
		expect(result.label).toBe('App on Android (Chrome)');
	});

	it('still reads sensibly when little is known about the installed app', () => {
		expect(describeDevice({ displayMode: 'standalone' }).label).toBe('App');
		expect(describeDevice({ platform: 'Android', displayMode: 'standalone' }).label).toBe(
			'App on Android'
		);
	});

	it('says nothing more for a browser tab or an older session', () => {
		expect(describeDevice({ userAgent: iphone, displayMode: 'browser' }).label).toBe(
			'Safari on iOS'
		);
		expect(describeDevice({ userAgent: iphone, displayMode: null }).label).toBe('Safari on iOS');
	});
});

function session(overrides: Partial<SessionResponse> = {}): SessionResponse {
	return {
		id: 's1',
		created_at: '2026-10-01T09:00:00Z',
		last_seen_at: '2026-10-10T12:00:00Z',
		expires_at: '2026-10-17T09:00:00Z',
		current: false,
		client_ip: '192.0.2.1',
		display_mode: 'standalone',
		...overrides
	};
}

function device(overrides: Partial<OwnDeviceResponse> = {}): OwnDeviceResponse {
	return {
		id: 'd1',
		user_agent: 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0',
		first_seen_at: '2026-09-01T08:00:00Z',
		last_seen_at: '2026-10-10T12:00:00Z',
		current: false,
		sessions: [session(), session({ id: 's0', client_ip: '192.0.2.9', display_mode: null })],
		...overrides
	};
}

describe('deviceRow', () => {
	it('describes a remembered browser from its newest session', () => {
		expect(deviceRow(device())).toEqual({
			label: 'App on Linux (Firefox)',
			kind: 'desktop',
			key: 'd1',
			deviceId: 'd1',
			name: null,
			title: 'App on Linux (Firefox)',
			subtitle: null,
			userAgent: device().user_agent,
			address: '192.0.2.1',
			firstSeen: '2026-09-01T08:00:00Z',
			lastSeen: '2026-10-10T12:00:00Z',
			current: false,
			sessionCount: 2,
			revoke: { kind: 'device', id: 'd1' }
		});
	});

	it('signs out an older session on its own', () => {
		const row = deviceRow(device({ id: null, sessions: [session({ id: 'legacy' })] }));
		expect(row.key).toBe('session-legacy');
		expect(row.revoke).toEqual({ kind: 'session', id: 'legacy' });
	});

	it('marks this device', () => {
		expect(deviceRow(device({ current: true })).current).toBe(true);
	});

	it('leads with the name and keeps the generated label as the subtitle', () => {
		const row = deviceRow(device({ name: "Sam's phone" }));
		expect(row.title).toBe("Sam's phone");
		expect(row.subtitle).toBe('App on Linux (Firefox)');
		expect(row.label).toBe('App on Linux (Firefox)');
	});

	it('cannot name a session from before devices were remembered', () => {
		const row = deviceRow(device({ id: null, sessions: [session({ id: 'legacy' })] }));
		expect(row.deviceId).toBeNull();
		expect(row.title).toBe(row.label);
		expect(row.subtitle).toBeNull();
	});
});

describe('nameDevice', () => {
	it('uses the name, or the generated label when there is none', () => {
		expect(nameDevice("Sam's phone", 'Chrome on Android')).toEqual({
			title: "Sam's phone",
			subtitle: 'Chrome on Android'
		});
		expect(nameDevice(null, 'Chrome on Android')).toEqual({
			title: 'Chrome on Android',
			subtitle: null
		});
		expect(nameDevice('   ', 'Chrome on Android').title).toBe('Chrome on Android');
	});
});
