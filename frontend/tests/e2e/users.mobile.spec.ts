import { expect, request, apiSessionOptions, sessionOptions, test, type Page } from './fixtures';
import { createUserViaApi, type E2EUser } from './helpers';

/** Users page on a phone: no sideways scroll, a confirm before Disable, and tappable actions. */
test.describe.configure({ mode: 'serial' });

const GUIDELINE_TARGET = 44;

const userRow = (page: Page, user: E2EUser) =>
	page
		.getByRole('list', { name: 'Users' })
		.getByRole('listitem')
		.filter({ hasText: user.username });

async function newUser(workerBaseURL: string, workerSession: Parameters<typeof sessionOptions>[1]) {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'mobile' });
	await adminApi.dispose();
	return user;
}

test('the users page does not scroll sideways', async ({ page, workerBaseURL, workerSession }) => {
	const user = await newUser(workerBaseURL, workerSession);
	await page.goto('/admin/users');
	await expect(userRow(page, user)).toBeVisible();
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});

test('row actions are at least 44px tall', async ({ page, workerBaseURL, workerSession }) => {
	const user = await newUser(workerBaseURL, workerSession);
	await page.goto('/admin/users');
	const row = userRow(page, user);
	for (const name of ['Disable', 'Reset password', 'Devices']) {
		const b = await row.getByRole('button', { name }).boundingBox();
		expect(b?.height ?? 0, name).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
	}
	const select = await row.getByLabel('Role').boundingBox();
	expect(select?.height ?? 0).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
});

test('the edit-name pencil is a full-size tap target and editing does not scroll sideways', async ({
	page,
	workerBaseURL,
	workerSession
}) => {
	const user = await newUser(workerBaseURL, workerSession);
	await page.goto('/admin/users');
	const row = userRow(page, user);
	const pencil = row.getByRole('button', { name: `Edit display name for ${user.username}` });
	const box = await pencil.boundingBox();
	expect(box?.width ?? 0).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
	expect(box?.height ?? 0).toBeGreaterThanOrEqual(GUIDELINE_TARGET);

	await pencil.click();
	const save = await row
		.getByRole('button', { name: `Save display name for ${user.username}` })
		.boundingBox();
	expect(save?.height ?? 0).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});

test('disabling asks first, and Cancel leaves the account alone', async ({
	page,
	workerBaseURL,
	workerSession
}) => {
	const user = await newUser(workerBaseURL, workerSession);
	await page.goto('/admin/users');
	const row = userRow(page, user);

	await row.getByRole('button', { name: 'Disable' }).click();
	const dialog = page.getByRole('dialog');
	await expect(dialog).toContainText(user.displayName);
	await expect(dialog).toContainText(
		'They will be signed out everywhere and cannot sign in until re-enabled.'
	);

	for (const name of ['Cancel', 'Disable']) {
		const b = await dialog.getByRole('button', { name, exact: true }).boundingBox();
		expect(b?.height ?? 0, name).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
	}

	await dialog.getByRole('button', { name: 'Cancel' }).click();
	await expect(dialog).toHaveCount(0);
	await expect(row.getByText('Disabled', { exact: true })).toHaveCount(0);
	await expect(row.getByRole('button', { name: 'Disable' })).toBeVisible();
});

test('confirming disables the account', async ({ page, workerBaseURL, workerSession }) => {
	const user = await newUser(workerBaseURL, workerSession);
	await page.goto('/admin/users');
	const row = userRow(page, user);

	await row.getByRole('button', { name: 'Disable' }).click();
	await page.getByRole('dialog').getByRole('button', { name: 'Disable', exact: true }).click();
	await expect(page.getByRole('dialog')).toHaveCount(0);
	await expect(row.getByText('Disabled', { exact: true })).toBeVisible();
	await expect(row.getByRole('button', { name: 'Enable' })).toBeVisible();
});

test('resetting a password asks first', async ({ page, workerBaseURL, workerSession }) => {
	const user = await newUser(workerBaseURL, workerSession);
	await page.goto('/admin/users');
	const row = userRow(page, user);

	await row.getByRole('button', { name: 'Reset password' }).click();
	const dialog = page.getByRole('dialog');
	await expect(dialog).toContainText(
		'They will be signed out everywhere and must choose a new password at next sign-in.'
	);
	await dialog.getByRole('button', { name: 'Cancel' }).click();
	await expect(dialog).toHaveCount(0);
	await expect(row.getByText('Must change password')).toHaveCount(0);
});

test('the password toggle is a full-size tap target in Add user', async ({ page }) => {
	await page.goto('/admin/users');
	await page.getByRole('button', { name: 'Add user' }).first().click();
	const toggle = page.getByRole('button', { name: 'Show password' });
	const box = await toggle.boundingBox();
	expect(box?.height ?? 0).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
	expect(box?.width ?? 0).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
});
