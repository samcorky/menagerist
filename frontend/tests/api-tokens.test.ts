import { describe, it, expect } from 'vitest';
import {
	AREAS,
	DEFAULT_EXPIRY_DAYS,
	EXPIRY_OPTIONS,
	TOKEN_PRESETS,
	describeExpiry,
	describeGrants,
	describeLastUsed,
	expiresSoon,
	grantsForPreset,
	grantsForSelection,
	sampleCurl,
	tokenErrorMessage
} from '../src/lib/api-tokens';

const GRANTABLE = [
	'graph:item:read',
	'graph:item:write',
	'graph:type:read',
	'graph:type:write',
	'collections:collection:read',
	'collections:collection:write',
	'media:item:read',
	'media:item:write',
	'presets:preset:read',
	'presets:preset:write',
	'examples:pack:read',
	'examples:pack:install'
];

describe('AREAS', () => {
	it('has plain labels with no colon or graph terms', () => {
		expect(AREAS.map((a) => a.label)).toEqual([
			'Items',
			'Item types',
			'Collections',
			'Media',
			'Presets',
			'Example packs'
		]);
		for (const area of AREAS) {
			expect(area.label).not.toContain(':');
			expect(area.label).not.toMatch(/node|edge|graph/i);
		}
	});

	it('covers every grantable permission exactly once', () => {
		const all = AREAS.flatMap((a) => [...a.read, ...a.write]);
		expect([...all].sort()).toEqual([...GRANTABLE].sort());
	});
});

describe('presets', () => {
	it('names the presets', () => {
		expect(TOKEN_PRESETS).toEqual({ read: 'Read only', readWrite: 'Read and write' });
	});

	it('read is every grantable read and no write', () => {
		const grants = grantsForPreset('read', GRANTABLE);
		expect(grants).toEqual([
			'graph:item:read',
			'graph:type:read',
			'collections:collection:read',
			'media:item:read',
			'presets:preset:read',
			'examples:pack:read'
		]);
	});

	it('readWrite is exactly the grantable list', () => {
		expect(grantsForPreset('readWrite', GRANTABLE)).toEqual(GRANTABLE);
	});

	it('never includes anything outside the grantable list', () => {
		const narrow = ['graph:item:read', 'media:item:write'];
		expect(grantsForPreset('readWrite', narrow)).toEqual(narrow);
		expect(grantsForPreset('read', narrow)).toEqual(['graph:item:read']);
		expect(grantsForPreset('readWrite', [])).toEqual([]);
	});
});

describe('grantsForSelection', () => {
	it('maps read and write, write implying read', () => {
		expect(
			grantsForSelection({ items: 'write', collections: 'read', media: 'none' }, GRANTABLE)
		).toEqual(['graph:item:read', 'graph:item:write', 'collections:collection:read']);
	});

	it('treats missing areas as none', () => {
		expect(grantsForSelection({}, GRANTABLE)).toEqual([]);
	});

	it('intersects with the grantable list', () => {
		expect(grantsForSelection({ items: 'write' }, ['graph:item:read', 'media:item:read'])).toEqual([
			'graph:item:read'
		]);
	});

	it('uses install as the example pack write', () => {
		expect(grantsForSelection({ example_packs: 'write' }, GRANTABLE)).toEqual([
			'examples:pack:read',
			'examples:pack:install'
		]);
	});
});

describe('describeGrants', () => {
	it('describes reads and writes in words', () => {
		expect(
			describeGrants(['graph:item:read', 'collections:collection:read', 'media:item:write'])
		).toBe('Read items and collections; write media');
	});

	it('groups read and write together', () => {
		expect(describeGrants(['graph:item:read', 'graph:item:write', 'media:item:read'])).toBe(
			'Read and write items; read media'
		);
	});

	it('lists three or more with an and', () => {
		expect(describeGrants(['presets:preset:read', 'graph:item:read', 'graph:type:read'])).toBe(
			'Read items, item types and presets'
		);
	});

	it('is stable regardless of input order', () => {
		expect(describeGrants([...GRANTABLE].reverse())).toBe(describeGrants(GRANTABLE));
	});

	it('never shows a raw permission', () => {
		expect(describeGrants(GRANTABLE)).not.toContain(':');
		expect(describeGrants(GRANTABLE)).toBe(
			'Read and write items, item types, collections, media, presets and example packs'
		);
	});

	it('ignores unknown strings and says so when nothing is left', () => {
		expect(describeGrants([])).toBe('No access');
		expect(describeGrants(['identity:user:create'])).toBe('No access');
	});
});

describe('expiry options', () => {
	it('offers 30, 90 and 365 days with 90 as the default', () => {
		expect(EXPIRY_OPTIONS.map((o) => o.days)).toEqual([30, 90, 365]);
		expect(DEFAULT_EXPIRY_DAYS).toBe(90);
		expect(EXPIRY_OPTIONS.map((o) => o.label)).toEqual(['30 days', '90 days', '1 year']);
	});
});

describe('describeExpiry and expiresSoon', () => {
	const now = new Date('2026-10-23T12:00:00Z');
	const at = (ms: number) => new Date(now.getTime() + ms).toISOString();
	const HOUR = 3_600_000;
	const DAY = 24 * HOUR;

	it('describes days ahead', () => {
		expect(describeExpiry(at(12 * DAY), now)).toBe('Expires in 12 days');
		expect(describeExpiry(at(90 * DAY), now)).toBe('Expires in 90 days');
	});

	it('describes tomorrow and today', () => {
		expect(describeExpiry(at(DAY), now)).toBe('Expires tomorrow');
		expect(describeExpiry(at(DAY - 1), now)).toBe('Expires today');
		expect(describeExpiry(at(HOUR), now)).toBe('Expires today');
	});

	it('says expired at and after the moment', () => {
		expect(describeExpiry(at(0), now)).toBe('Expired');
		expect(describeExpiry(at(-DAY), now)).toBe('Expired');
	});

	it('flags tokens expiring within 14 days', () => {
		expect(expiresSoon(at(14 * DAY), now)).toBe(true);
		expect(expiresSoon(at(14 * DAY + 1), now)).toBe(false);
		expect(expiresSoon(at(1), now)).toBe(true);
	});

	it('does not flag expired tokens', () => {
		expect(expiresSoon(at(0), now)).toBe(false);
		expect(expiresSoon(at(-1), now)).toBe(false);
		expect(expiresSoon(at(-DAY), now)).toBe(false);
	});
});

describe('describeLastUsed', () => {
	const now = new Date(2026, 9, 23, 12, 0, 0);
	const local = (day: number, hour = 12) => new Date(2026, 9, day, hour).toISOString();

	it('says never used for null and undefined', () => {
		expect(describeLastUsed(null, now)).toBe('Never used');
		expect(describeLastUsed(undefined, now)).toBe('Never used');
	});

	it('says used today for the same calendar day', () => {
		expect(describeLastUsed(local(23, 0), now)).toBe('Used today');
		expect(describeLastUsed(local(23, 13), now)).toBe('Used today');
	});

	it('counts calendar days', () => {
		expect(describeLastUsed(local(22, 23), now)).toBe('Used yesterday');
		expect(describeLastUsed(local(20), now)).toBe('Used 3 days ago');
		expect(describeLastUsed(local(9), now)).toBe('Used 14 days ago');
	});
});

describe('tokenErrorMessage', () => {
	const res = (status: number, headers: Record<string, string> = {}) =>
		new Response(null, { status, headers });

	it('explains a wrong password', () => {
		expect(
			tokenErrorMessage({
				error: {
					title: 'CurrentPasswordIncorrectError',
					detail: 'The current password is incorrect.'
				},
				response: res(400)
			})
		).toBe('That password is not right.');
	});

	it('explains throttling with and without a retry hint', () => {
		expect(tokenErrorMessage({ error: {}, response: res(429, { 'Retry-After': '120' }) })).toBe(
			'Too many attempts. Try again in 2 minutes.'
		);
		expect(tokenErrorMessage({ error: {}, response: res(429) })).toBe(
			'Too many attempts. Wait a little while, then try again.'
		);
	});

	it('explains the token limit', () => {
		expect(tokenErrorMessage({ error: {}, response: res(409) })).toBe(
			'You have reached the limit of active tokens. Revoke one you no longer use, then try again.'
		);
	});

	it('includes the server detail for an invalid request', () => {
		expect(
			tokenErrorMessage({
				error: { title: 'InvalidApiTokenRequestError', detail: 'Choose a shorter lifetime.' },
				response: res(400)
			})
		).toBe("That request isn't valid. Choose a shorter lifetime.");
	});

	it('explains a network failure', () => {
		expect(tokenErrorMessage({ error: undefined, response: undefined })).toBe(
			'You appear to be offline. Check your connection and try again.'
		);
	});

	it('handles a missing token and server errors', () => {
		expect(tokenErrorMessage({ error: {}, response: res(404) })).toBe(
			'That token no longer exists. Reload the page.'
		);
		expect(tokenErrorMessage({ error: {}, response: res(500) })).toBe(
			'Something went wrong. Try again in a moment.'
		);
	});
});

describe('sampleCurl', () => {
	it('calls the permissions endpoint with the real token as a bearer header', () => {
		const text = sampleCurl('https://example.test', 'mnst_secret123');
		expect(text).toContain('https://example.test/api/v1/auth/me/permissions');
		expect(text).toContain('Authorization: Bearer mnst_secret123');
	});
});
