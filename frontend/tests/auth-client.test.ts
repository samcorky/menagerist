import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '../src/lib/auth.svelte';
import { clearAllEtags, getEtag, setEtag } from '../src/lib/api/etagStore';
import { resetAuthEvents } from '../src/lib/api/auth-events';
import { client } from '../src/lib/api/generated/client.gen';

const json = (body: unknown, init: ResponseInit = {}) =>
	new Response(JSON.stringify(body), {
		status: 200,
		headers: { 'Content-Type': 'application/json' },
		...init
	});

const problem = (status: number, type: string, headers: Record<string, string> = {}) =>
	new Response(
		JSON.stringify({ type, title: 't', status, detail: 'Plain words.', instance: 'i' }),
		{
			status,
			headers: { 'Content-Type': 'application/problem+json', ...headers }
		}
	);

const user = {
	id: 'u1',
	username: 'sam',
	display_name: 'Sam',
	role: 'admin',
	password_expired: false,
	disabled: false,
	created_at: '',
	updated_at: ''
};

beforeEach(() => {
	vi.stubGlobal('document', { cookie: 'a=1; menagerist_csrf=tok123' });
	resetAuthEvents();
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('CSRF header', () => {
	it('is sent on unsafe methods only', async () => {
		const seen: Record<string, string | null> = {};
		vi.stubGlobal('fetch', async (request: Request) => {
			seen[request.method] = request.headers.get('X-CSRF-Token');
			return json({});
		});
		await client.get({ url: '/api/v1/thing' });
		await client.post({ url: '/api/v1/thing', body: {} });
		await client.put({ url: '/api/v1/thing', body: {} });
		await client.patch({ url: '/api/v1/thing', body: {} });
		await client.delete({ url: '/api/v1/thing' });
		expect(seen).toEqual({
			GET: null,
			POST: 'tok123',
			PUT: 'tok123',
			PATCH: 'tok123',
			DELETE: 'tok123'
		});
	});

	it('is omitted when there is no CSRF cookie', async () => {
		vi.stubGlobal('document', { cookie: '' });
		let header: string | null = 'unset';
		vi.stubGlobal('fetch', async (request: Request) => {
			header = request.headers.get('X-CSRF-Token');
			return json({});
		});
		await client.post({ url: '/api/v1/thing', body: {} });
		expect(header).toBeNull();
	});
});

describe('401 handling', () => {
	it('signs out once for a burst of 401s', async () => {
		vi.stubGlobal('fetch', async () => problem(401, 'unauthenticated'));
		auth.user = user as never;
		auth.permissions = new Set(['graph:node_type:delete']);
		await Promise.all([
			client.get({ url: '/api/v1/a' }),
			client.get({ url: '/api/v1/b' }),
			client.get({ url: '/api/v1/c' })
		]);
		expect(auth.user).toBeNull();
		expect(auth.can('graph:node_type:delete')).toBe(false);

		// Handled already: a later 401 does nothing until a fresh sign-in resets it.
		auth.user = user as never;
		await client.get({ url: '/api/v1/d' });
		expect(auth.user).not.toBeNull();
		auth.user = null;
	});

	it('ignores a 401 from sign-in itself', async () => {
		auth.user = user as never;
		vi.stubGlobal('fetch', async () => problem(401, 'about:blank'));
		const result = await auth.signIn('sam', 'wrong');
		expect(result).toEqual({ ok: false, message: 'Plain words.' });
		expect(auth.user).not.toBeNull();
		auth.user = null;
	});

	it('flags setup required', async () => {
		vi.stubGlobal('fetch', async () => problem(401, 'setup_required'));
		await client.get({ url: '/api/v1/a' });
		expect(auth.setupRequired).toBe(true);
		auth.setupRequired = false;
	});

	it('marks the password expired on a 403 password_expired', async () => {
		auth.user = user as never;
		vi.stubGlobal('fetch', async () => problem(403, 'password_expired'));
		await client.get({ url: '/api/v1/items' });
		expect(auth.passwordExpired).toBe(true);
		auth.user = null;
	});
});

describe('sign-in and sign-out clear the cache', () => {
	it('clears cached bodies on sign-in', async () => {
		setEtag('/api/v1/node', { etag: '"v1"', data: { secret: 1 } });
		vi.stubGlobal('fetch', async (request: Request) =>
			new URL(request.url).pathname.endsWith('/auth/me/permissions')
				? json({ permissions: [] })
				: json(user)
		);
		const result = await auth.signIn('sam', 'a-long-password');
		expect(result.ok).toBe(true);
		expect(getEtag('/api/v1/node')).toBeUndefined();
		expect(auth.user?.username).toBe('sam');
	});

	it('clears cached bodies on sign-out and drops the account', async () => {
		auth.user = user as never;
		setEtag('/api/v1/node', { etag: '"v1"', data: { secret: 1 } });
		vi.stubGlobal('fetch', async () => new Response(null, { status: 204 }));
		const result = await auth.signOut();
		expect(result.ok).toBe(true);
		expect(getEtag('/api/v1/node')).toBeUndefined();
		expect(auth.user).toBeNull();
		expect(auth.leftOnPurpose).toBe(true);
	});
});

describe('can()', () => {
	it('reflects the loaded permissions and skips them when the password is expired', async () => {
		vi.stubGlobal('fetch', async (request: Request) =>
			new URL(request.url).pathname.endsWith('/permissions')
				? json({ permissions: ['graph:node_type:delete'] })
				: json(user)
		);
		await auth.refresh();
		expect(auth.can('graph:node_type:delete')).toBe(true);
		expect(auth.can('graph:edge_type:delete')).toBe(false);

		const paths: string[] = [];
		vi.stubGlobal('fetch', async (request: Request) => {
			paths.push(new URL(request.url).pathname);
			return json({ ...user, password_expired: true });
		});
		await auth.refresh();
		expect(auth.passwordExpired).toBe(true);
		expect(auth.can('graph:node_type:delete')).toBe(false);
		expect(paths).toEqual(['/api/v1/auth/me']);
		auth.user = null;
	});
});

describe('429 on sign-in', () => {
	it('shows the wait in minutes', async () => {
		vi.stubGlobal('fetch', async () => problem(429, 'about:blank', { 'Retry-After': '300' }));
		const result = await auth.signIn('sam', 'x');
		expect(result).toEqual({ ok: false, message: 'Too many attempts. Try again in 5 minutes.' });
	});
});

describe('more auth behaviour', () => {
	it('clears the cache on a 401-forced sign-out', async () => {
		auth.user = user as never;
		setEtag('/api/v1/node', { etag: '"v1"', data: { secret: 1 } });
		vi.stubGlobal('fetch', async () => problem(401, 'unauthenticated'));
		await client.get({ url: '/api/v1/a' });
		expect(getEtag('/api/v1/node')).toBeUndefined();
		expect(auth.user).toBeNull();
	});

	it('follows a changed CSRF cookie between requests', async () => {
		const seen: (string | null)[] = [];
		vi.stubGlobal('fetch', async (request: Request) => {
			seen.push(request.headers.get('X-CSRF-Token'));
			return json({});
		});
		await client.post({ url: '/api/v1/thing', body: {} });
		vi.stubGlobal('document', { cookie: 'menagerist_csrf=rotated' });
		await client.post({ url: '/api/v1/thing', body: {} });
		expect(seen).toEqual(['tok123', 'rotated']);
	});

	it('ignores a 403 that is not password_expired', async () => {
		auth.user = user as never;
		vi.stubGlobal('fetch', async () => problem(403, 'csrf_failed'));
		await client.post({ url: '/api/v1/thing', body: {} });
		expect(auth.passwordExpired).toBe(false);
		expect(auth.user).not.toBeNull();
		auth.user = null;
	});

	it('treats a 401 from /auth/me during init as signed out', async () => {
		auth.ready = false;
		vi.stubGlobal('fetch', async (request: Request) =>
			new URL(request.url).pathname.endsWith('/auth/status')
				? json({ setup_required: false })
				: problem(401, 'unauthenticated')
		);
		await auth.init();
		expect(auth.ready).toBe(true);
		expect(auth.loadFailed).toBe(false);
		expect(auth.user).toBeNull();
	});

	it('gives a generic message for a 429 without Retry-After', async () => {
		vi.stubGlobal('fetch', async () => problem(429, 'about:blank'));
		const result = await auth.signIn('sam', 'x');
		expect(result).toEqual({
			ok: false,
			message: 'Too many attempts. Wait a little while, then try again.'
		});
	});

	it('fails sign-out on a server error and keeps the account', async () => {
		auth.user = user as never;
		vi.stubGlobal('fetch', async () => problem(500, 'about:blank'));
		const result = await auth.signOut();
		expect(result.ok).toBe(false);
		expect(auth.user).not.toBeNull();
		auth.user = null;
	});

	it('treats a 401 on sign-out as already signed out', async () => {
		auth.user = user as never;
		vi.stubGlobal('fetch', async () => problem(401, 'unauthenticated'));
		expect((await auth.signOut()).ok).toBe(true);
		expect(auth.user).toBeNull();
	});

	it('reports an error when the account cannot be loaded after signing in', async () => {
		vi.stubGlobal('fetch', async (request: Request) =>
			new URL(request.url).pathname.endsWith('/auth/login')
				? json(user)
				: problem(500, 'about:blank')
		);
		const result = await auth.signIn('sam', 'a-long-password');
		expect(result.ok).toBe(false);
		expect(auth.user).toBeNull();
	});

	it('keeps setupRequired set until the session is loaded', async () => {
		auth.setupRequired = true;
		let during: boolean | null = null;
		vi.stubGlobal('fetch', async (request: Request) => {
			const path = new URL(request.url).pathname;
			if (path.endsWith('/auth/me')) during = auth.setupRequired;
			return path.endsWith('/permissions') ? json({ permissions: [] }) : json(user);
		});
		await auth.finishSetup();
		expect(during).toBe(true);
		expect(auth.setupRequired).toBe(false);
		expect(auth.user).not.toBeNull();
		auth.user = null;
	});

	it('does not cache a GET that was in flight when the cache was cleared', async () => {
		let release!: () => void;
		const gate = new Promise<void>((r) => (release = r));
		let started!: () => void;
		const inFlight = new Promise<void>((r) => (started = r));
		vi.stubGlobal('fetch', async () => {
			started();
			await gate;
			return json({ secret: 1 }, { headers: { 'Content-Type': 'application/json', ETag: '"v1"' } });
		});
		const pending = client.get({ url: '/api/v1/slow' });
		await inFlight;
		clearAllEtags();
		release();
		await pending;
		expect(getEtag('/api/v1/slow')).toBeUndefined();

		// A request started after the clear is cached as usual.
		vi.stubGlobal('fetch', async () =>
			json({ ok: 1 }, { headers: { 'Content-Type': 'application/json', ETag: '"v2"' } })
		);
		await client.get({ url: '/api/v1/fresh' });
		expect(getEtag('/api/v1/fresh')?.etag).toBe('"v2"');
	});
});
