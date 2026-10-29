import { expect, request, apiSessionOptions, signInViaApi, test, type Page } from './fixtures';
import { asUser, createUserViaApi, type E2EUser } from './helpers';

/**
 * Sign-in visibility and account upkeep: last sign-in, display name, disabled and locked accounts.
 * Deliberate sign-in failures are kept to the minimum: the per-address throttle is shared by every
 * spec, so nothing here loops.
 */
test.describe.configure({ mode: 'serial' });

const userRow = (page: Page, user: E2EUser) =>
	page.getByRole('table', { name: 'Users' }).getByRole('row').filter({ hasText: user.username });

async function signInThroughForm(page: Page, username: string, password: string) {
	await page.getByLabel('Username').fill(username);
	await page.getByLabel('Password', { exact: true }).fill(password);
	await page.getByRole('button', { name: 'Sign in', exact: true }).click();
}

test('an administrator sees when a user last signed in', async ({
	page,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'seen' });
	await adminApi.dispose();

	await page.goto('/admin/users');
	// The table's own "Last sign-in" column holds the value; someone who has just signed in is not "Never".
	await expect(page.getByRole('table', { name: 'Users' })).toContainText('Last sign-in');
	await expect(userRow(page, user)).not.toContainText('Never');
});

test('a display-name change shows in the user menu at once', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'rename' });
	await adminApi.dispose();

	const { page, context } = await asUser(browser, user);
	await page.goto('/settings/account');
	await page.getByLabel('Name', { exact: true }).fill('   ');
	await expect(page.getByText('A display name must be 1 to 120 characters.')).toBeVisible();

	const renamed = `Renamed ${Date.now()}`;
	await page.getByLabel('Name', { exact: true }).fill(renamed);
	await page.getByRole('button', { name: 'Save name' }).click();
	await expect(page.getByText('Display name updated')).toBeVisible();
	await expect(page.getByRole('button', { name: `Account menu for ${renamed}` })).toBeVisible();
	await context.close();
});

test('an administrator renames another user from the users page', async ({
	page,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'renamed-by-admin' });
	await adminApi.dispose();

	await page.goto('/admin/users');
	const row = userRow(page, user);
	await row.getByRole('button', { name: `Edit display name for ${user.username}` }).click();
	const field = row.getByRole('textbox', { name: `Display name for ${user.username}` });
	await expect(field).toBeFocused();

	const renamed = `Renamed by admin ${Date.now()}`;
	await field.fill(renamed);
	await field.press('Enter');
	await expect(page.getByText('Name updated')).toBeVisible();
	await expect(row.getByText(renamed, { exact: true })).toBeVisible();
	await expect(
		row.getByRole('button', { name: `Edit display name for ${user.username}` })
	).toBeFocused();

	await page.reload();
	await expect(userRow(page, user).getByText(renamed, { exact: true })).toBeVisible();
});

test('Escape cancels a rename without saving', async ({ page, workerBaseURL, workerSession }) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'rename-escape' });
	await adminApi.dispose();

	await page.goto('/admin/users');
	const row = userRow(page, user);
	await row.getByRole('button', { name: `Edit display name for ${user.username}` }).click();
	const field = row.getByRole('textbox', { name: `Display name for ${user.username}` });
	await field.fill('Should not be saved');
	await field.press('Escape');
	await expect(field).toHaveCount(0);
	await expect(row.getByText(user.displayName, { exact: true })).toBeVisible();
	await page.reload();
	await expect(userRow(page, user).getByText(user.displayName, { exact: true })).toBeVisible();
});

test('a blank name shows a message and keeps the editor open', async ({
	page,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'rename-blank' });
	await adminApi.dispose();

	await page.goto('/admin/users');
	const row = userRow(page, user);
	await row.getByRole('button', { name: `Edit display name for ${user.username}` }).click();
	const field = row.getByRole('textbox', { name: `Display name for ${user.username}` });
	await field.fill('   ');
	await field.press('Enter');
	await expect(row.getByRole('alert')).toContainText('A display name must be 1 to 120 characters.');
	await expect(field).toBeVisible();
});

test('a disabled account sees why, and a wrong password stays generic', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'disabled' });
	const res = await adminApi.patch(`/api/v1/user/${user.id}`, { data: { disabled: true } });
	expect(res.ok(), await res.text()).toBeTruthy();
	await adminApi.dispose();

	const anonymous = await browser.newContext({
		baseURL: workerBaseURL,
		storageState: { cookies: [], origins: [] },
		extraHTTPHeaders: {}
	});
	const login = await anonymous.newPage();
	await login.goto('/login');
	await signInThroughForm(login, user.username, user.password);
	await expect(
		login.getByText('This account has been disabled. Ask an administrator.')
	).toBeVisible();

	await signInThroughForm(login, user.username, 'definitely-not-it-1');
	await expect(login.getByText('Incorrect username or password.')).toBeVisible();
	await expect(login.getByText('has been disabled')).toHaveCount(0);
	await anonymous.close();
});

test('an administrator unlocks a locked-out account', async ({
	page,
	playwright,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'locked' });
	await adminApi.dispose();

	const anonymous = await playwright.request.newContext({ baseURL: workerBaseURL });
	for (let attempt = 0; attempt < 5; attempt++) {
		const res = await anonymous.post('/api/v1/auth/login', {
			data: { username: user.username, password: 'definitely-not-it-1' }
		});
		expect(res.status()).toBe(401);
	}
	const locked = await anonymous.post('/api/v1/auth/login', {
		data: { username: user.username, password: user.password }
	});
	expect(locked.status()).toBe(429);
	await anonymous.dispose();

	await page.goto('/admin/users');
	const row = userRow(page, user);
	await expect(row.getByText(/^Locked until/)).toBeVisible();
	await row.getByRole('button', { name: 'Unlock' }).click();
	await expect(page.getByText('Account unlocked')).toBeVisible();
	await expect(row.getByText(/^Locked until/)).toHaveCount(0);
	await expect(row.getByRole('button', { name: 'Unlock' })).toHaveCount(0);

	await signInViaApi(workerBaseURL, user.username, user.password);
});

test('the password toggle shows and hides the typed text without submitting', async ({
	browser,
	workerBaseURL
}) => {
	const anonymous = await browser.newContext({
		baseURL: workerBaseURL,
		storageState: { cookies: [], origins: [] },
		extraHTTPHeaders: {}
	});
	const login = await anonymous.newPage();
	let submitted = false;
	await login.route('**/api/v1/auth/login', (route) => {
		submitted = true;
		return route.abort();
	});
	await login.goto('/login');

	const field = login.getByLabel('Password', { exact: true });
	await field.fill('not-a-real-one');
	await expect(field).toHaveAttribute('type', 'password');

	const show = login.getByRole('button', { name: 'Show password' });
	await expect(show).toHaveAttribute('aria-pressed', 'false');
	await show.click();
	const hide = login.getByRole('button', { name: 'Hide password' });
	await expect(hide).toHaveAttribute('aria-pressed', 'true');
	await expect(field).toHaveAttribute('type', 'text');
	await expect(field).toHaveValue('not-a-real-one');

	// Keyboard: the toggle follows the field in tab order and Space flips it back.
	await field.focus();
	await login.keyboard.press('Tab');
	await expect(hide).toBeFocused();
	await login.keyboard.press('Space');
	await expect(field).toHaveAttribute('type', 'password');
	await expect(login.getByRole('button', { name: 'Show password' })).toBeVisible();
	expect(submitted).toBe(false);
	await expect(login).toHaveURL(/\/login/);
	await anonymous.close();
});
