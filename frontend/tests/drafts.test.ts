import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearDraft, clearDrafts, readDraft, registerDraft, saveDrafts } from '../src/lib/drafts';
import { auth } from '../src/lib/auth.svelte';
import { resetAuthEvents } from '../src/lib/api/auth-events';
import { client } from '../src/lib/api/generated/client.gen';

/** A sessionStorage stand-in with the parts the draft store uses. */
function memoryStorage() {
	const items = new Map<string, string>();
	return {
		get length() {
			return items.size;
		},
		key: (i: number) => [...items.keys()][i] ?? null,
		getItem: (k: string) => items.get(k) ?? null,
		setItem: (k: string, v: string) => void items.set(k, v),
		removeItem: (k: string) => void items.delete(k),
		items
	};
}

let storage: ReturnType<typeof memoryStorage>;
const cleanups: Array<() => void> = [];

beforeEach(() => {
	storage = memoryStorage();
	vi.stubGlobal('sessionStorage', storage);
	resetAuthEvents();
});

afterEach(() => {
	while (cleanups.length) cleanups.pop()!();
	vi.unstubAllGlobals();
	auth.user = null;
	auth.leftOnPurpose = false;
	auth.sessionExpired = false;
});

function register(key: string, snapshot: () => unknown) {
	cleanups.push(registerDraft(key, snapshot));
}

describe('the draft store', () => {
	it('keeps what each open form has, under its owner, and skips forms with nothing', () => {
		register('item:new', () => ({ name: 'Poster' }));
		register('item:1', () => null);
		saveDrafts('u1');
		expect(readDraft('u1', 'item:new')).toEqual({ name: 'Poster' });
		expect(readDraft('u1', 'item:1')).toBeNull();
		expect(readDraft('u2', 'item:new')).toBeNull();
	});

	it('stops asking a form once it has gone', () => {
		const unregister = registerDraft('item:new', () => ({ name: 'Poster' }));
		unregister();
		saveDrafts('u1');
		expect(storage.items.size).toBe(0);
	});

	it('leaves a newer registration for the same form in place', () => {
		const first = registerDraft('item:new', () => ({ name: 'old' }));
		register('item:new', () => ({ name: 'new' }));
		first();
		saveDrafts('u1');
		expect(readDraft('u1', 'item:new')).toEqual({ name: 'new' });
	});

	it('forgets one draft, everyone else’s, or all of them', () => {
		register('item:new', () => ({ name: 'Poster' }));
		register('item:1', () => ({ name: 'Lamp' }));
		saveDrafts('u1');
		saveDrafts('u2');
		storage.setItem('menagerist:open-section', '1');

		clearDraft('u1', 'item:1');
		expect(readDraft('u1', 'item:1')).toBeNull();
		expect(readDraft('u1', 'item:new')).not.toBeNull();

		clearDrafts('u1');
		expect(readDraft('u1', 'item:new')).not.toBeNull();
		expect(readDraft('u2', 'item:new')).toBeNull();

		clearDrafts();
		expect([...storage.items.keys()]).toEqual(['menagerist:open-section']);
	});

	it('loses nothing but the draft when storage is blocked or holds junk', () => {
		register('item:new', () => ({ name: 'Poster' }));
		storage.setItem('menagerist:draft:u1:item:1', '{not json');
		expect(readDraft('u1', 'item:1')).toBeNull();

		vi.stubGlobal('sessionStorage', undefined);
		expect(() => saveDrafts('u1')).not.toThrow();
		expect(readDraft('u1', 'item:new')).toBeNull();
		expect(() => clearDraft('u1', 'item:new')).not.toThrow();
		expect(() => clearDrafts()).not.toThrow();
	});
});

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

describe('drafts and the session', () => {
	it('are kept when the server ends the session', async () => {
		register('item:new', () => ({ name: 'Poster' }));
		auth.user = user as never;
		vi.stubGlobal('fetch', async () => new Response(null, { status: 401 }));
		await client.get({ url: '/api/v1/a' });
		expect(auth.sessionExpired).toBe(true);
		expect(readDraft('u1', 'item:new')).toEqual({ name: 'Poster' });
	});

	it('are not kept, and old ones go, when the person signs out', async () => {
		storage.setItem('menagerist:draft:u1:item:1', '{}');
		register('item:new', () => ({ name: 'Poster' }));
		auth.user = user as never;
		vi.stubGlobal('fetch', async () => new Response(null, { status: 204 }));
		await auth.signOut();
		expect(storage.items.size).toBe(0);
	});

	it('belong only to the account that signs in next', async () => {
		storage.setItem('menagerist:draft:u1:item:1', '{}');
		storage.setItem('menagerist:draft:u2:item:1', '{}');
		vi.stubGlobal('fetch', async (request: Request) =>
			new URL(request.url).pathname.endsWith('/permissions')
				? Response.json({ permissions: [] })
				: Response.json(user)
		);
		expect((await auth.signIn('sam', 'a-long-password')).ok).toBe(true);
		expect([...storage.items.keys()]).toEqual(['menagerist:draft:u1:item:1']);
	});
});
