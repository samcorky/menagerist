import { expect, request, apiSessionOptions, test } from './fixtures';
import { asUser, createUserViaApi } from './helpers';

/**
 * Administrator device management: viewing all active devices, per-user device dialog,
 * revoking user devices, and permission gating for non-administrators.
 */
test.describe.configure({ mode: 'serial' });

test('an administrator can view all active devices and revoke a member device', async ({
	page,
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const member = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'admin-dev-member' });
	await adminApi.dispose();

	const memberSession = await asUser(browser, member);

	// Administrator visits /admin/devices
	await page.goto('/admin/devices');
	await expect(page.getByRole('heading', { name: 'Devices' })).toBeVisible();

	// Locate member's device row/card
	const memberRow = page.locator('tr, li').filter({ hasText: member.displayName });
	await expect(memberRow.first()).toBeVisible();

	// Revoke member's device
	await memberRow.first().getByRole('button', { name: 'Sign out' }).click();
	await expect(page.getByText('Device signed out')).toBeVisible();

	// Member is now signed out on their next navigation
	await memberSession.page.goto('/settings/account');
	await expect(memberSession.page).toHaveURL(/\/login/);

	await memberSession.context.close();
});

test('an administrator can view and revoke devices from the users page dialog', async ({
	page,
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const member = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'admin-user-dev' });
	await adminApi.dispose();

	const memberSession = await asUser(browser, member);

	await page.goto('/admin/users');
	const userRow = page
		.getByRole('list', { name: 'Users' })
		.getByRole('listitem')
		.filter({ hasText: member.username });

	await userRow.getByRole('button', { name: 'Devices' }).click();
	const dialog = page.getByRole('dialog');
	await expect(dialog).toContainText(`Devices for ${member.displayName}`);

	// Sign out member device from dialog
	await dialog.getByRole('button', { name: 'Sign out' }).click();
	await expect(page.getByText('Device signed out')).toBeVisible();

	// Member is now signed out
	await memberSession.page.goto('/settings/account');
	await expect(memberSession.page).toHaveURL(/\/login/);

	await memberSession.context.close();
});

test('a member sees no admin area and cannot access admin routes', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const member = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'plain-member' });
	await adminApi.dispose();

	const memberSession = await asUser(browser, member);

	// Member navigates to /admin
	await memberSession.page.goto('/admin');
	await expect(
		memberSession.page.getByText('Only administrators can access this area.')
	).toBeVisible();

	// Member navigates to /admin/devices
	await memberSession.page.goto('/admin/devices');
	await expect(
		memberSession.page.getByText(
			'Only administrators with session management permissions can access this page.'
		)
	).toBeVisible();

	// Member navigates to /admin/users
	await memberSession.page.goto('/admin/users');
	await expect(
		memberSession.page
			.getByRole('alert')
			.filter({ hasText: 'Only administrators can manage users.' })
	).toBeVisible();

	await memberSession.context.close();
});

test('filtering by user on /admin/devices narrows the listed devices', async ({
	page,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const userA = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'filter-a' });
	const userB = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'filter-b' });
	await adminApi.dispose();

	await page.goto('/admin/devices');
	const devices = page.getByRole('table', { name: 'Active devices' });
	const userARow = devices.getByRole('row').filter({ hasText: userA.displayName });
	const userBRow = devices.getByRole('row').filter({ hasText: userB.displayName });
	await expect(userARow).toBeVisible();
	await expect(userBRow).toBeVisible();

	// Select userA in filter
	await page.getByLabel('Filter by user').selectOption(userA.id);
	await expect(userARow).toBeVisible();
	await expect(userBRow).toHaveCount(0);

	// Select All users
	await page.getByLabel('Filter by user').selectOption('');
	await expect(userARow).toBeVisible();
	await expect(userBRow).toBeVisible();
});
