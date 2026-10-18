import {
	test as base,
	request as playwrightRequest,
	type APIRequestContext,
	type Browser,
	type BrowserContext,
	type Page
} from '@playwright/test';

export * from '@playwright/test';

/** Backend port of worker 0; worker i listens on this + i (see playwright.config.ts). */
export const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8100);

/** Backend port of the `auth` project (its own empty database, see auth.spec.ts). */
export const AUTH_BACKEND_PORT = Number(process.env.E2E_AUTH_BACKEND_PORT ?? 8190);

export const CSRF_COOKIE = 'menagerist_csrf';
export const CSRF_HEADER = 'X-CSRF-Token';

export type Credentials = { username: string; displayName: string; password: string };

/** The administrator every worker database is set up with (the password is the stable constant). */
export const E2E_ADMIN: Credentials = {
	username: 'e2e-admin',
	displayName: 'E2E Admin',
	password: 'e2e-admin-password-1'
};

type StorageState = Awaited<ReturnType<APIRequestContext['storageState']>>;
export type Session = { storageState: StorageState; csrf: string };

/** The context options that make a browser context or API context act as a signed-in user. */
export function sessionOptions(baseURL: string, session: Session) {
	return {
		baseURL,
		storageState: session.storageState,
		extraHTTPHeaders: { [CSRF_HEADER]: session.csrf }
	};
}

async function captureSession(api: APIRequestContext): Promise<Session> {
	const storageState = await api.storageState();
	const csrf = storageState.cookies.find((c) => c.name === CSRF_COOKIE)?.value;
	if (!csrf) throw new Error('The server did not set a CSRF cookie.');
	return { storageState, csrf };
}

/** Signs in through the API and returns the session; throws on bad credentials. */
export async function signInViaApi(
	baseURL: string,
	username: string,
	password: string
): Promise<Session> {
	const api = await playwrightRequest.newContext({ baseURL });
	try {
		const res = await api.post('/api/v1/auth/login', { data: { username, password } });
		if (!res.ok()) throw new Error(`Sign-in as ${username} failed with ${res.status()}.`);
		return await captureSession(api);
	} finally {
		await api.dispose();
	}
}

/** Changes the password of the account `session` belongs to and returns its new session. */
export async function changePasswordViaApi(
	baseURL: string,
	session: Session,
	current: string,
	next: string
): Promise<Session> {
	const api = await playwrightRequest.newContext({
		...sessionOptions(baseURL, session)
	});
	try {
		const res = await api.post('/api/v1/auth/password', {
			data: { current_password: current, new_password: next }
		});
		if (!res.ok()) throw new Error(`Password change failed with ${res.status()}.`);
		return await captureSession(api);
	} finally {
		await api.dispose();
	}
}

/**
 * Makes sure the backend at `baseURL` has the e2e administrator and returns their session. A
 * fresh database goes through the real first-run setup; one that already has users signs in.
 */
export async function ensureAdminSession(baseURL: string): Promise<Session> {
	const api = await playwrightRequest.newContext({ baseURL });
	try {
		const status = await api.get('/api/v1/auth/status');
		const { setup_required } = (await status.json()) as { setup_required: boolean };
		const res = setup_required
			? await api.post('/api/v1/auth/setup', {
					data: {
						username: E2E_ADMIN.username,
						display_name: E2E_ADMIN.displayName,
						password: E2E_ADMIN.password
					}
				})
			: await api.post('/api/v1/auth/login', {
					data: { username: E2E_ADMIN.username, password: E2E_ADMIN.password }
				});
		if (!res.ok()) {
			throw new Error(
				`Could not ${setup_required ? 'set up' : 'sign in to'} the e2e database at ${baseURL} ` +
					`(${res.status()}). If it was created by an older run with a different admin ` +
					`password, drop the e2e volume with "uv run poe e2e-db-down" and migrate again.`
			);
		}
		return await captureSession(api);
	} finally {
		await api.dispose();
	}
}

/**
 * Each worker has its own backend (serving the built SPA) and database, so `baseURL` follows
 * `parallelIndex`. The worker signs in once as the e2e admin (setting the database up on its
 * first run); `page` and `request` then both carry that session and its CSRF header.
 */
export const test = base.extend<object, { workerBaseURL: string; workerSession: Session }>({
	workerBaseURL: [
		// eslint-disable-next-line no-empty-pattern -- Playwright parses the first argument
		async ({}, use, workerInfo) => {
			await use(`http://localhost:${BACKEND_PORT + workerInfo.parallelIndex}`);
		},
		{ scope: 'worker' }
	],
	workerSession: [
		async ({ workerBaseURL }, use) => {
			await use(await ensureAdminSession(workerBaseURL));
		},
		{ scope: 'worker' }
	],
	baseURL: async ({ workerBaseURL }, use) => {
		await use(workerBaseURL);
	},
	storageState: async ({ workerSession }, use) => {
		await use(workerSession.storageState);
	},
	extraHTTPHeaders: async ({ workerSession }, use) => {
		await use({ [CSRF_HEADER]: workerSession.csrf });
	}
});

export type SignedInUser = { page: Page; context: BrowserContext; request: APIRequestContext };

/** Open a signed-in browser context for a non-admin session. */
export async function openSession(
	browser: Browser,
	baseURL: string,
	session: Session
): Promise<SignedInUser> {
	const context = await browser.newContext(sessionOptions(baseURL, session));
	const page = await context.newPage();
	return { page, context, request: context.request };
}
