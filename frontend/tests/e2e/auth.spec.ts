import { expect, request, test, type Page } from '@playwright/test';
import { sessionOptions, signInViaApi } from './fixtures';
import { createUserViaApi, type E2EUser } from './helpers';

/**
 * Runs in the `auth` project against its own backend and an empty database (menagerist_auth),
 * so the first-run setup is real. The tests build on each other, so the file is serial.
 *
 * The database is recreated empty by `poe e2e-migrate` (part of `poe test-e2e`). Running the
 * file twice without migrating in between skips it, with a note saying so.
 */
test.describe.configure({ mode: 'serial' });

const ADMIN = { name: 'Auth Admin', username: 'auth-admin', password: 'auth-admin-pass-1' };

let baseURL = '';
let member: E2EUser;
let newcomer: E2EUser;

const accountMenu = (page: Page, name: string) =>
	page.getByRole('button', { name: `Account menu for ${name}` });

async function signInThroughForm(page: Page, username: string, password: string) {
	await page.getByLabel('Username').fill(username);
	await page.getByLabel('Password', { exact: true }).fill(password);
	await page.getByRole('button', { name: 'Sign in', exact: true }).click();
}

/** The page goes to /login at once; the server's answer follows, so wait for it too. */
async function clickSignOut(page: Page) {
	const answered = page.waitForResponse((r) => r.url().endsWith('/api/v1/auth/logout'));
	await page.getByRole('menuitem', { name: 'Sign out' }).click();
	await expect(page).toHaveURL(/\/login/);
	expect((await answered).status()).toBe(204);
}

async function signOut(page: Page, name: string) {
	await accountMenu(page, name).click();
	await clickSignOut(page);
}

/** Opens /login and, if a session from an earlier test is still active, signs out of it. */
async function startSignedOut(page: Page) {
	await page.goto('/login');
	const menu = page.getByRole('button', { name: /^Account menu for / });
	await expect(menu.or(page.getByLabel('Username'))).toBeVisible();
	if (await menu.isVisible()) {
		await menu.click();
		await clickSignOut(page);
	}
}

async function adminApi() {
	const session = await signInViaApi(baseURL, ADMIN.username, ADMIN.password);
	return request.newContext(sessionOptions(baseURL, session));
}

test.beforeAll(async ({ playwright }, testInfo) => {
	baseURL = String(testInfo.project.use.baseURL);
	const api = await playwright.request.newContext({ baseURL });
	const res = await api.get('/api/v1/auth/status');
	const { setup_required } = (await res.json()) as { setup_required: boolean };
	await api.dispose();
	test.skip(
		!setup_required,
		'The auth database already has users. Run "E2E_WORKERS=1 uv run poe e2e-migrate" to recreate it empty.'
	);
});

test('first visit goes to setup, creates the administrator and signs them in', async ({ page }) => {
	await page.goto('/items');
	await expect(page).toHaveURL(/\/setup$/);
	await expect(page.getByRole('heading', { name: 'Welcome to Menagerist' })).toBeVisible();

	await page.getByLabel('Your name').fill(ADMIN.name);
	await page.getByLabel('Username').fill(ADMIN.username);
	await page.getByLabel('Password', { exact: true }).fill(ADMIN.password);
	await page.getByLabel('Confirm password').fill('something else entirely');
	await expect(page.getByText('The passwords do not match.')).toBeVisible();
	await expect(page.getByRole('button', { name: 'Create account' })).toBeDisabled();
	await page.getByLabel('Confirm password').fill(ADMIN.password);
	await page.getByRole('button', { name: 'Create account' }).click();

	// A database with existing data shows what was claimed first; an empty one goes straight in.
	const carryOn = page.getByRole('button', { name: 'Continue' });
	const menu = accountMenu(page, ADMIN.name);
	await expect(carryOn.or(menu)).toBeVisible();
	if (await carryOn.isVisible()) {
		await expect(page.getByText('Everything that was already here is now yours')).toBeVisible();
		await carryOn.click();
	}
	await expect(menu).toBeVisible();
	await expect(page).not.toHaveURL(/\/(setup|login)/);
});

test('setup cannot be run again', async ({ page }) => {
	await page.goto('/setup');
	// Signed in already, so the guard moves on; the API itself refuses a second setup.
	await expect(page).not.toHaveURL(/\/setup/);
	const res = await page.request.post('/api/v1/auth/setup', {
		data: { username: 'second', display_name: 'Second', password: 'second-admin-pass-1' }
	});
	expect(res.status()).toBe(409);
});

test('signs out, and a wrong password is refused with a plain message', async ({ page }) => {
	await startSignedOut(page);
	await signInThroughForm(page, ADMIN.username, 'definitely-not-it-1');
	await expect(page.getByText('Incorrect username or password.')).toBeVisible();
	await expect(page).toHaveURL(/\/login/);

	// The same message for an account that does not exist.
	await signInThroughForm(page, 'nobody-here', 'definitely-not-it-1');
	await expect(page.getByText('Incorrect username or password.')).toBeVisible();

	await signInThroughForm(page, ADMIN.username, ADMIN.password);
	await expect(accountMenu(page, ADMIN.name)).toBeVisible();
	await expect(page).not.toHaveURL(/\/login/);

	await signOut(page, ADMIN.name);
	await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
});

test('an invalid session sends you to sign in and back to the page you wanted', async ({
	page,
	context
}) => {
	await startSignedOut(page);
	await signInThroughForm(page, ADMIN.username, ADMIN.password);
	await expect(accountMenu(page, ADMIN.name)).toBeVisible();

	const sessionCookies = (await context.cookies(baseURL)).filter(
		(c) => c.name === 'menagerist_session'
	);
	expect(sessionCookies).toHaveLength(1);
	await context.addCookies(
		sessionCookies.map((c) => ({ ...c, value: 'not-a-real-session-token' }))
	);

	await page.goto('/collections');
	await expect(page).toHaveURL(/\/login\?next=%2Fcollections$/);

	await signInThroughForm(page, ADMIN.username, ADMIN.password);
	await expect(page).toHaveURL(/\/collections$/);
	await expect(accountMenu(page, ADMIN.name)).toBeVisible();
});

test('a new account must choose its own password before carrying on', async ({ page }) => {
	const admin = await adminApi();
	newcomer = await createUserViaApi(admin, baseURL, {
		prefix: 'newcomer',
		keepStartingPassword: true
	});
	member = await createUserViaApi(admin, baseURL, { prefix: 'member' });
	await admin.dispose();

	await startSignedOut(page);
	await signInThroughForm(page, newcomer.username, newcomer.password);

	await expect(page).toHaveURL(/\/settings\/account$/);
	await expect(page.getByText('Choose a new password')).toBeVisible();

	// Other pages bounce back to the account page until the password is changed.
	await page.goto('/items');
	await expect(page).toHaveURL(/\/settings\/account$/);

	const next = 'a-brand-new-password-9';
	await page.getByLabel('Current password').fill(newcomer.password);
	await page.getByLabel('New password', { exact: true }).fill(next);
	await page.getByLabel('Confirm new password').fill(next);
	await page.getByRole('button', { name: 'Change password' }).click();

	await expect(page.getByText('Password changed')).toBeVisible();
	await expect(page).toHaveURL(/\/$/);
	await expect(accountMenu(page, newcomer.displayName)).toBeVisible();

	await page.goto('/items');
	await expect(page).toHaveURL(/\/items$/);

	// The new password works at the next sign-in.
	await signOut(page, newcomer.displayName);
	await signInThroughForm(page, newcomer.username, next);
	await expect(accountMenu(page, newcomer.displayName)).toBeVisible();
});

test('a member does not see the Users page', async ({ page }) => {
	await startSignedOut(page);
	await signInThroughForm(page, member.username, member.password);
	await expect(accountMenu(page, member.displayName)).toBeVisible();

	await accountMenu(page, member.displayName).click();
	await expect(page.getByRole('menuitem', { name: 'Account' })).toBeVisible();
	await expect(page.getByRole('menuitem', { name: 'Administration' })).toHaveCount(0);
	await page.keyboard.press('Escape');

	await page.goto('/admin/users');
	await expect(page.getByText('Only administrators can manage users.')).toBeVisible();
});

test('an administrator sees the Users page', async ({ page }) => {
	await startSignedOut(page);
	await signInThroughForm(page, ADMIN.username, ADMIN.password);
	await accountMenu(page, ADMIN.name).click();
	await page.getByRole('menuitem', { name: 'Administration' }).click();
	await expect(page).toHaveURL(/\/admin$/);
	await page.getByRole('link', { name: /Users/ }).click();
	await expect(page).toHaveURL(/\/admin\/users$/);
	await expect(page.getByRole('list', { name: 'Users' })).toContainText(member.username);
});

test('signing out ends the session: the protected page asks you to sign in again', async ({
	page
}) => {
	await startSignedOut(page);
	await signInThroughForm(page, ADMIN.username, ADMIN.password);
	await expect(accountMenu(page, ADMIN.name)).toBeVisible();
	await page.goto('/items');
	await expect(accountMenu(page, ADMIN.name)).toBeVisible();

	await signOut(page, ADMIN.name);
	await page.goto('/items');
	await expect(page).toHaveURL(/\/login\?next=%2Fitems$/);
	await page.reload();
	await expect(page).toHaveURL(/\/login\?next=%2Fitems$/);

	const res = await page.request.get('/api/v1/node');
	expect(res.status()).toBe(401);
});
