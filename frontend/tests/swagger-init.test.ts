import { beforeAll, describe, expect, it } from 'vitest';
import { fileURLToPath } from 'node:url';

/** A minimal DOM: enough to prove the banner is built from text nodes, never markup. */
class FakeNode {
	className = '';
	children: FakeNode[] = [];
	attrs: Record<string, string> = {};
	listeners: Record<string, () => void> = {};
	private text = '';
	constructor(readonly tag: string) {}
	set textContent(value: string) {
		this.text = value;
	}
	get textContent(): string {
		return this.text + this.children.map((c) => c.textContent).join('');
	}
	set innerHTML(_value: string) {
		throw new Error('innerHTML must not be used');
	}
	appendChild(child: FakeNode) {
		this.children.push(child);
	}
	replaceChildren(...nodes: FakeNode[]) {
		this.children = nodes;
	}
	setAttribute(name: string, value: string) {
		this.attrs[name] = value;
	}
	addEventListener(name: string, fn: () => void) {
		this.listeners[name] = fn;
	}
}
type FakeDocument = { createElement(tag: string): FakeNode };

type Init = {
	prepareRequest(
		req: { method: string; url: string; headers?: Record<string, string>; credentials?: string },
		origin: string
	): { headers?: Record<string, string>; credentials?: string };
	isSessionChange(url: string, origin: string): boolean;
	fetchJson(
		url: string,
		allow401: boolean,
		fetchFn: (url: string, init: object) => Promise<unknown>
	): Promise<unknown>;
	bannerModel(
		status: { setup_required: boolean } | null,
		me: { display_name: string; role: string; password_expired: boolean } | null,
		failed?: boolean,
		notice?: string,
		checking?: boolean
	): {
		tone: string;
		text: string;
		notice?: string;
		busy?: boolean;
		actions: { label: string; href?: string; action?: string }[];
	};
	loginHref(): string;
	safeLogoUrl(logo: unknown, origin?: string): string | null;
	cookieSchemes(definitions: Record<string, { type?: string; in?: string }>): string[];
	applyLocks(ui: unknown, names: string[], signedIn: boolean): void;
	renderBanner(
		doc: FakeDocument,
		box: FakeNode,
		model: ReturnType<Init['bannerModel']>,
		onSignOut: () => void
	): FakeNode;
};

// The script is the backend's static Swagger UI setup; it attaches its helpers to globalThis.
const SCRIPT = fileURLToPath(
	new URL('../../backend/src/app/entrypoints/api/docs/static/swagger-init.js', import.meta.url)
);
const ORIGIN = 'http://localhost:8000';
let init: Init;

beforeAll(async () => {
	await import(/* @vite-ignore */ SCRIPT);
	init = (globalThis as unknown as { MenageristSwaggerInit: Init }).MenageristSwaggerInit;
});

describe('swagger-init prepareRequest', () => {
	it('sends same-origin credentials', () => {
		const req = init.prepareRequest(
			{ method: 'POST', url: `${ORIGIN}/api/v1/collection`, headers: {} },
			ORIGIN
		);
		expect(req.credentials).toBe('same-origin');
	});

	it('adds the origin for the curl snippet and sends no CSRF header', () => {
		const req = init.prepareRequest(
			{ method: 'POST', url: `${ORIGIN}/api/v1/collection`, headers: { A: '1' } },
			ORIGIN
		);
		expect(req.headers).toEqual({ A: '1', Origin: ORIGIN });
		expect(Object.keys(req.headers ?? {}).map((k) => k.toLowerCase())).not.toContain(
			'x-csrf-token'
		);
	});

	it('copes with a request that has no headers', () => {
		const req = init.prepareRequest({ method: 'GET', url: '/api/v1/x' }, ORIGIN);
		expect(req.headers).toEqual({ Origin: ORIGIN });
	});
});

describe('swagger-init fetchJson', () => {
	const reply =
		(status: number, body: unknown = {}) =>
		() =>
			Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });

	it('returns the body on success', async () => {
		await expect(init.fetchJson('/x', true, reply(200, { a: 1 }))).resolves.toEqual({ a: 1 });
	});

	it('treats 401 as signed out only when allowed', async () => {
		await expect(init.fetchJson('/x', true, reply(401))).resolves.toBeNull();
		await expect(init.fetchJson('/x', false, reply(401))).rejects.toThrow();
	});

	it('rejects other statuses and network errors', async () => {
		await expect(init.fetchJson('/x', true, reply(500))).rejects.toThrow();
		await expect(
			init.fetchJson('/x', true, () => Promise.reject(new Error('net')))
		).rejects.toThrow();
	});
});

describe('swagger-init session banner', () => {
	it('recognises session-changing responses', () => {
		expect(init.isSessionChange(`${ORIGIN}/api/v1/auth/login`, ORIGIN)).toBe(true);
		expect(init.isSessionChange(`${ORIGIN}/api/v1/auth/password`, ORIGIN)).toBe(true);
		expect(init.isSessionChange(`${ORIGIN}/api/v1/auth/me`, ORIGIN)).toBe(false);
	});

	const me = { display_name: 'Ada', role: 'admin', password_expired: false };

	it('offers sign in with an encoded next when signed out', () => {
		const model = init.bannerModel({ setup_required: false }, null);
		expect(model.tone).toBe('warn');
		expect(model.text).toMatch(/^Not signed in/);
		expect(model.actions).toEqual([{ label: 'Sign in', href: '/login?next=%2Fapi%2Fdocs' }]);
		expect(init.loginHref()).toBe('/login?next=%2Fapi%2Fdocs');
	});

	it('offers setup on a first run', () => {
		const model = init.bannerModel({ setup_required: true }, null);
		expect(model.text).toMatch(/^First run/);
		expect(model.actions).toEqual([{ label: 'Set up', href: '/setup' }]);
	});

	it('offers the account page when the password has expired', () => {
		const model = init.bannerModel(null, { ...me, password_expired: true });
		expect(model.text).toMatch(/^Password change required/);
		expect(model.actions).toEqual([{ label: 'Change password', href: '/settings/account' }]);
	});

	it('shows the person with open and sign-out actions when signed in', () => {
		const model = init.bannerModel({ setup_required: false }, me);
		expect(model.tone).toBe('ok');
		expect(model.text).toBe('Signed in as Ada (admin)');
		expect(model.actions).toEqual([
			{ label: 'Open Menagerist', href: '/' },
			{ label: 'Sign out', action: 'signout' }
		]);
	});

	it('reports a failed check as an error with no actions', () => {
		expect(init.bannerModel(null, null, true)).toEqual({
			tone: 'error',
			text: 'Could not check the sign-in state.',
			actions: []
		});
	});

	it('only accepts a same-origin logo path', () => {
		const ok = (url: unknown) => init.safeLogoUrl({ url }, ORIGIN);
		expect(ok('/api/docs/logo.svg')).toBe('/api/docs/logo.svg');
		for (const bad of [
			'//evil.example/x.svg',
			'/\\evil.example',
			'/\t/evil.example/x.svg',
			'/\n/evil.example/x.svg',
			'/\r/evil.example/x.svg',
			'/ /evil.example/x.svg',
			'/\u0000/evil.example',
			'https://evil.example/x.svg',
			'javascript:alert(1)',
			'data:image/svg+xml,<svg/>',
			'',
			'logo.svg'
		]) {
			expect(ok(bad), JSON.stringify(bad)).toBeNull();
		}
		for (const bad of [undefined, null, 5, {}, []]) expect(ok(bad)).toBeNull();
		expect(init.safeLogoUrl(null, ORIGIN)).toBeNull();
		expect(init.safeLogoUrl(undefined, ORIGIN)).toBeNull();
	});

	it('picks only apiKey-in-cookie schemes', () => {
		expect(
			init.cookieSchemes({
				APIKeyCookie: { type: 'apiKey', in: 'cookie' },
				Header: { type: 'apiKey', in: 'header' },
				Bearer: { type: 'http' }
			})
		).toEqual(['APIKeyCookie']);
		expect(init.cookieSchemes({})).toEqual([]);
	});

	it('applies locks per scheme and survives a throwing Swagger', () => {
		const calls: string[] = [];
		const ui = {
			preauthorizeApiKey: (name: string, value: string) => calls.push(`pre:${name}:${value}`),
			authActions: { logout: (names: string[]) => calls.push(`out:${names.join()}`) }
		};
		init.applyLocks(ui, ['A'], true);
		init.applyLocks(ui, ['A'], false);
		expect(calls).toEqual(['pre:A:session', 'out:A']);
		const throwing = {
			preauthorizeApiKey: () => {
				throw new Error('boom');
			},
			authActions: {
				logout: () => {
					throw new Error('boom');
				}
			}
		};
		expect(() => init.applyLocks(throwing, ['A', 'B'], true)).not.toThrow();
		expect(() => init.applyLocks(throwing, ['A', 'B'], false)).not.toThrow();
	});

	it('shows a sign-out failure on the signed-in banner', () => {
		const model = init.bannerModel({ setup_required: false }, me, false, 'Could not sign out.');
		expect(model.tone).toBe('error');
		expect(model.notice).toBe('Could not sign out.');
		expect(model.actions).toHaveLength(2);
	});

	it('renders a hostile display name as text, never markup', () => {
		const hostile = '<img src=x onerror=alert(1)>';
		const doc: FakeDocument = { createElement: (tag) => new FakeNode(tag) };
		const box = new FakeNode('div');
		const model = init.bannerModel(
			null,
			{ display_name: hostile, role: 'member', password_expired: false },
			false,
			'<b>notice</b>'
		);
		init.renderBanner(doc, box, model, () => {});
		expect(box.textContent).toContain(hostile);
		expect(box.textContent).toContain('<b>notice</b>');
		const tags: string[] = [];
		const walk = (n: FakeNode) => {
			tags.push(n.tag);
			n.children.forEach(walk);
		};
		box.children.forEach(walk);
		expect(tags).not.toContain('img');
		expect(tags).not.toContain('b');
		expect(box.className).toBe('menagerist-session menagerist-session-error');
	});

	it('shows a busy, action-free state while the sign-in state is being checked', () => {
		expect(init.bannerModel(null, null, false, '', true)).toEqual({
			tone: 'info',
			text: 'Checking sign-in state…',
			busy: true,
			actions: []
		});
	});

	it('checks again rather than showing a stale signed-in state', () => {
		const model = init.bannerModel({ setup_required: false }, me, false, '', true);
		expect(model.busy).toBe(true);
		expect(model.actions).toEqual([]);
	});

	it('marks the live region busy and adds a hidden spinner only while checking', () => {
		const doc: FakeDocument = { createElement: (tag) => new FakeNode(tag) };
		const box = new FakeNode('div');
		init.renderBanner(doc, box, init.bannerModel(null, null, false, '', true), () => {});
		expect(box.className).toBe('menagerist-session menagerist-session-info');
		expect(box.attrs['aria-busy']).toBe('true');
		const nodes: FakeNode[] = [];
		const walk = (n: FakeNode) => {
			nodes.push(n);
			n.children.forEach(walk);
		};
		box.children.forEach(walk);
		const spinner = nodes.find((n) => n.className === 'menagerist-spinner');
		expect(spinner?.attrs['aria-hidden']).toBe('true');
		expect(nodes.some((n) => n.tag === 'a' || n.tag === 'button')).toBe(false);
		expect(box.textContent).toContain('Checking sign-in state…');

		init.renderBanner(doc, box, init.bannerModel(null, null, false), () => {});
		expect(box.attrs['aria-busy']).toBe('false');
		const after: FakeNode[] = [];
		const walkAfter = (n: FakeNode) => {
			after.push(n);
			n.children.forEach(walkAfter);
		};
		box.children.forEach(walkAfter);
		expect(after.some((n) => n.className === 'menagerist-spinner')).toBe(false);
	});

	it('wires the sign-out button and link targets', () => {
		const doc: FakeDocument = { createElement: (tag) => new FakeNode(tag) };
		const box = new FakeNode('div');
		let clicked = 0;
		init.renderBanner(doc, box, init.bannerModel(null, me, false), () => clicked++);
		const nodes: FakeNode[] = [];
		const walk = (n: FakeNode) => {
			nodes.push(n);
			n.children.forEach(walk);
		};
		box.children.forEach(walk);
		nodes.find((n) => n.tag === 'button')?.listeners.click();
		expect(clicked).toBe(1);
		expect(nodes.find((n) => n.tag === 'a')?.attrs.href).toBe('/');
	});
});

describe('swagger-init cookie header', () => {
	it('drops the placeholder Cookie header Swagger adds for the lock', () => {
		const req = init.prepareRequest(
			{
				method: 'GET',
				url: '/api/v1/x',
				headers: { Cookie: 'menagerist-session=session', A: '1' }
			},
			ORIGIN
		);
		expect(req.headers).toEqual({ A: '1', Origin: ORIGIN });
	});
});
