import { describe, it, expect } from 'vitest';
import { describeDevice } from '../src/lib/devices';

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
