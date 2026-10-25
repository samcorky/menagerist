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
		checking?: boolean,
		token?: { status: string; count?: number } | null
	): {
		tone: string;
		text: string;
		sessionText: string;
		notice?: string;
		busy?: boolean;
		actions: { label: string; href?: string; action?: string }[];
		sessionActions: { label: string; href?: string; action?: string }[];
	};
	checkToken(
		token: string,
		fetchFn: (
			url: string,
			init: { headers: Record<string, string>; credentials: string }
		) => Promise<unknown>
	): Promise<{ status: string; count?: number }>;
	bearerSchemes(definitions: Record<string, { type?: string; scheme?: string }>): string[];
	bearerToken(authorized: Record<string, { value?: unknown }>, names: string[]): string;
	hintSchemeBlocks(doc: FakeDocument, container: unknown, names: string[]): void;
	loginHref(): string;
	safeLogoUrl(logo: unknown, origin?: string): string | null;
	cookieSchemes(definitions: Record<string, { type?: string; in?: string }>): string[];
	applyLocks(ui: unknown, names: string[], signedIn: boolean): void;
	renderDialogSession(
		doc: FakeDocument,
		section: FakeNode,
		model: ReturnType<Init['bannerModel']>,
		onSignOut: () => void
	): FakeNode;
	hideSchemeBlocks(container: unknown, names: string[]): number;
	evaluateExpression(expression: string, body: unknown): string | undefined;
	responseBody(response: unknown): unknown;
	findOperation(
		paths: Record<string, Record<string, { operationId?: string }>>,
		operationId: string
	): { path: string; method: string } | null;
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

	it('points at Authorize when signed out, with no banner buttons', () => {
		const model = init.bannerModel({ setup_required: false }, null);
		expect(model.tone).toBe('warn');
		expect(model.text).toBe('Not signed in. Use Authorize to sign in or add an API token.');
		expect(model.actions).toEqual([]);
		expect(model.sessionText).toBe('Not signed in.');
		expect(model.sessionActions).toEqual([{ label: 'Sign in', href: '/login?next=%2Fapi%2Fdocs' }]);
		expect(init.loginHref()).toBe('/login?next=%2Fapi%2Fdocs');
	});

	it('points at Authorize to set up on a first run', () => {
		const model = init.bannerModel({ setup_required: true }, null);
		expect(model.text).toBe(
			'First run: create the administrator account. Use Authorize to set up.'
		);
		expect(model.actions).toEqual([]);
		expect(model.sessionActions).toEqual([{ label: 'Set up', href: '/setup' }]);
	});

	it('offers the account page when the password has expired', () => {
		const model = init.bannerModel(null, { ...me, password_expired: true });
		expect(model.text).toMatch(/^Password change required/);
		expect(model.actions).toEqual([{ label: 'Change password', href: '/settings/account' }]);
	});

	it('shows the person with open and sign-out actions when signed in', () => {
		const model = init.bannerModel({ setup_required: false }, me);
		expect(model.tone).toBe('ok');
		expect(model.text).toBe('Signed in as Ada (browser session).');
		expect(model.actions).toEqual([
			{ label: 'Open Menagerist', href: '/' },
			{ label: 'Sign out', action: 'signout' }
		]);
		expect(model.sessionActions).toEqual([{ label: 'Sign out', action: 'signout' }]);
	});

	describe('with an API token', () => {
		const out = { setup_required: false };
		const rejected = 'This API token was not accepted (invalid, expired or revoked).';

		it('says it is checking a token while signed out', () => {
			const model = init.bannerModel(out, null, false, '', false, { status: 'checking' });
			expect(model.text).toBe('Using an API token.');
			expect(model.tone).toBe('info');
			expect(model.actions).toEqual([]);
		});

		it('counts the permissions of an accepted token', () => {
			const ok = (count: number) =>
				init.bannerModel(out, null, false, '', false, { status: 'ok', count });
			expect(ok(3).text).toBe('Using an API token with 3 permissions.');
			expect(ok(3).tone).toBe('ok');
			expect(ok(1).text).toBe('Using an API token with 1 permission.');
		});

		it('warns when the token is rejected and when it could not be checked', () => {
			const bad = init.bannerModel(out, null, false, '', false, { status: 'rejected' });
			expect(bad.tone).toBe('warn');
			expect(bad.text).toBe(rejected);
			const down = init.bannerModel(out, null, false, '', false, { status: 'failed' });
			expect(down.tone).toBe('error');
			expect(down.text).toBe('Could not check the API token.');
		});

		it('prefers the token text over the first-run hint', () => {
			const model = init.bannerModel({ setup_required: true }, null, false, '', false, {
				status: 'ok',
				count: 2
			});
			expect(model.text).toBe('Using an API token with 2 permissions.');
		});

		it('says the token takes precedence when signed in as well', () => {
			const both = init.bannerModel(out, me, false, '', false, { status: 'ok', count: 4 });
			expect(both.text).toBe(
				'Signed in as Ada. An API token is also set and takes precedence for Try it out.'
			);
			expect(both.tone).toBe('ok');
			expect(both.sessionText).toBe('Signed in as Ada (browser session).');
			expect(both.actions.map((a) => a.label)).toEqual(['Open Menagerist', 'Sign out']);
		});

		it('appends the failure when the token is also bad', () => {
			const bad = init.bannerModel(out, me, false, '', false, { status: 'rejected' });
			expect(bad.tone).toBe('warn');
			expect(bad.text).toMatch(/^Signed in as Ada\. An API token is also set/);
			expect(bad.text.endsWith(rejected)).toBe(true);
			const down = init.bannerModel(out, me, false, '', false, { status: 'failed' });
			expect(down.text.endsWith('Could not check the API token.')).toBe(true);
		});

		it('finds bearer schemes and the token Swagger holds, and never invents one', () => {
			expect(
				init.bearerSchemes({
					HTTPBearer: { type: 'http', scheme: 'bearer' },
					Basic: { type: 'http', scheme: 'basic' },
					Cookie: { type: 'apiKey' }
				})
			).toEqual(['HTTPBearer']);
			expect(init.bearerSchemes({})).toEqual([]);
			expect(init.bearerToken({ HTTPBearer: { value: 'mnst_x' } }, ['HTTPBearer'])).toBe('mnst_x');
			expect(init.bearerToken({ HTTPBearer: { value: '' } }, ['HTTPBearer'])).toBe('');
			expect(init.bearerToken({ Other: { value: 'x' } }, ['HTTPBearer'])).toBe('');
			expect(init.bearerToken({}, [])).toBe('');
		});

		describe('checkToken', () => {
			const reply =
				(status: number, body: unknown = {}) =>
				() =>
					Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });

			it('sends the bearer header without cookies and counts the permissions', async () => {
				let seen: { url: string; credentials: string; auth: string } | undefined;
				const result = await init.checkToken('mnst_secret', (url, options) => {
					seen = { url, credentials: options.credentials, auth: options.headers.Authorization };
					return reply(200, { permissions: ['a:b:c', 'd:e:f'] })();
				});
				expect(result).toEqual({ status: 'ok', count: 2 });
				expect(seen?.url).toBe('/api/v1/auth/me/permissions');
				expect(seen?.credentials).toBe('omit');
				expect(seen?.auth).toBe('Bearer mnst_secret');
				expect(seen?.url).not.toContain('mnst_secret');
			});

			it('maps 401 to rejected and anything else to failed', async () => {
				await expect(init.checkToken('t', reply(401))).resolves.toEqual({ status: 'rejected' });
				await expect(init.checkToken('t', reply(500))).resolves.toEqual({ status: 'failed' });
				await expect(init.checkToken('t', reply(200, { nope: 1 }))).resolves.toEqual({
					status: 'failed'
				});
				await expect(init.checkToken('t', () => Promise.reject(new Error('net')))).resolves.toEqual(
					{ status: 'failed' }
				);
			});
		});

		it('adds the token hint under the bearer heading once', () => {
			const doc: FakeDocument = { createElement: (tag) => new FakeNode(tag) };
			const inserted: { tag: string; text: string; before: unknown }[] = [];
			const heading = {
				textContent: 'HTTPBearer (http, Bearer)',
				nextSibling: 'NEXT',
				parentNode: {
					insertBefore: (n: FakeNode, ref: unknown) =>
						inserted.push({ tag: n.tag, text: n.textContent, before: ref })
				}
			};
			let hinted = false;
			const block = {
				hidden: false,
				querySelector: (sel: string) => (sel === 'h4' ? heading : hinted ? {} : null)
			};
			const container = { querySelectorAll: () => [block] };
			init.hintSchemeBlocks(doc, container, ['HTTPBearer']);
			hinted = true;
			init.hintSchemeBlocks(doc, container, ['HTTPBearer']);
			expect(inserted).toEqual([
				{ tag: 'p', text: 'Or use a token instead of a session.', before: 'NEXT' }
			]);
		});
	});

	it('reports a failed check as an error with no actions', () => {
		expect(init.bannerModel(null, null, true)).toMatchObject({
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

	it('hides the named scheme blocks in the Authorize dialog and no others', () => {
		const block = (title: string) => ({
			hidden: false,
			querySelector: () => ({ textContent: title })
		});
		const cookie = block('APIKeyCookie\u00a0(apiKey)');
		const bearer = block('HTTPBearer (http, Bearer)');
		const container = { querySelectorAll: () => [cookie, bearer] };
		expect(init.hideSchemeBlocks(container, ['APIKeyCookie'])).toBe(1);
		expect(cookie.hidden).toBe(true);
		expect(bearer.hidden).toBe(false);
		expect(init.hideSchemeBlocks(container, [])).toBe(0);
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
		const model = init.bannerModel(null, null, false, '', true);
		expect(model).toMatchObject({
			tone: 'info',
			text: 'Checking sign-in state…',
			busy: true,
			actions: [],
			sessionActions: []
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

	describe('dialog session block', () => {
		const doc: FakeDocument = { createElement: (tag) => new FakeNode(tag) };
		const me = { display_name: 'Alice', role: 'member', password_expired: false };
		const all = (root: FakeNode) => {
			const found: FakeNode[] = [];
			const walk = (n: FakeNode) => {
				found.push(n);
				n.children.forEach(walk);
			};
			root.children.forEach(walk);
			return found;
		};

		it('uses Swagger block classes with a primary Sign in link when signed out', () => {
			const section = new FakeNode('div');
			init.renderDialogSession(doc, section, init.bannerModel(null, null, false), () => {});
			expect(section.className).toBe('auth-container');
			const nodes = all(section);
			expect(nodes.find((n) => n.tag === 'h4')?.textContent).toBe('Browser session');
			expect(nodes.some((n) => n.tag === 'h6')).toBe(false);
			expect(nodes.find((n) => n.tag === 'p')?.textContent).toContain('Not signed in');
			expect(nodes.filter((n) => n.tag === 'p').at(-1)?.textContent).toBe(
				'An API token, when set below, takes precedence over the session for Try it out.'
			);
			// The dialog shows the session only, even when a token is set.
			const withToken = new FakeNode('div');
			init.renderDialogSession(
				doc,
				withToken,
				init.bannerModel(null, null, false, '', false, { status: 'ok', count: 2 }),
				() => {}
			);
			expect(withToken.textContent).toContain('Not signed in.');
			expect(withToken.textContent).not.toContain('Using an API token');
			const link = nodes.find((n) => n.tag === 'a');
			expect(link?.className).toBe('btn modal-btn auth authorize button');
			expect(link?.attrs.href).toBe('/login?next=%2Fapi%2Fdocs');
			expect(nodes.some((n) => n.className === 'auth-btn-wrapper')).toBe(true);
		});

		it('shows a plain Sign out button, the name and a failure notice when signed in', () => {
			const section = new FakeNode('div');
			let clicked = 0;
			init.renderDialogSession(
				doc,
				section,
				init.bannerModel(null, me, false, 'Could not sign out.'),
				() => clicked++
			);
			const nodes = all(section);
			const button = nodes.find((n) => n.tag === 'button');
			expect(button?.className).toBe('btn modal-btn auth button');
			button?.listeners.click();
			expect(clicked).toBe(1);
			const lines = nodes.filter((n) => n.tag === 'p').map((n) => n.textContent);
			expect(lines[0]).toBe('Signed in as Alice (browser session).');
			expect(lines[1]).toBe('Could not sign out.');
			expect(nodes.find((n) => n.className === 'menagerist-session-notice')).toBeDefined();
		});

		it('is busy with no buttons while checking, and shows the setup hint', () => {
			const section = new FakeNode('div');
			init.renderDialogSession(
				doc,
				section,
				init.bannerModel(null, null, false, '', true),
				() => {}
			);
			expect(section.attrs['aria-busy']).toBe('true');
			expect(all(section).some((n) => n.tag === 'a' || n.tag === 'button')).toBe(false);
			expect(section.textContent).toContain('Checking sign-in state…');
			init.renderDialogSession(
				doc,
				section,
				init.bannerModel({ setup_required: true }, null, false),
				() => {}
			);
			expect(section.attrs['aria-busy']).toBe('false');
			expect(section.textContent).toContain('First run');
			expect(all(section).find((n) => n.tag === 'a')?.attrs.href).toBe('/setup');
		});
	});
});

describe('swagger-init link helpers', () => {
	it('evaluates $response.body pointers', () => {
		const body = { id: 'a', items: [{ id: 'b' }], 'a/b': { 'c~d': 7 }, nested: { x: 1 } };
		expect(init.evaluateExpression('$response.body#/id', body)).toBe('a');
		expect(init.evaluateExpression('$response.body#/items/0/id', body)).toBe('b');
		expect(init.evaluateExpression('$response.body#/a~1b/c~0d', body)).toBe('7');
		expect(init.evaluateExpression('$response.body#/0/id', [{ id: 'z' }])).toBe('z');
	});

	it('gives undefined for anything else', () => {
		const body = { id: 'a', nested: { x: 1 } };
		expect(init.evaluateExpression('$response.body#/missing', body)).toBeUndefined();
		expect(init.evaluateExpression('$response.body#/nested', body)).toBeUndefined();
		expect(init.evaluateExpression('$request.path.id', body)).toBeUndefined();
		expect(init.evaluateExpression('$response.body#/id', undefined)).toBeUndefined();
	});

	it('reads a response body from the parsed body or the text', () => {
		expect(init.responseBody({ body: { id: 1 } })).toEqual({ id: 1 });
		expect(init.responseBody({ text: '{"id":2}' })).toEqual({ id: 2 });
		expect(init.responseBody({ text: 'not json' })).toBeUndefined();
		expect(init.responseBody(undefined)).toBeUndefined();
	});

	it('finds an operation by its id', () => {
		const paths = {
			'/a': { get: { operationId: 'one' } },
			'/b/{id}': { delete: { operationId: 'two' } }
		};
		expect(init.findOperation(paths, 'two')).toMatchObject({ path: '/b/{id}', method: 'delete' });
		expect(init.findOperation(paths, 'nope')).toBeNull();
	});
});
