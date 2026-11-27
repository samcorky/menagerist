import { expect, request, apiSessionOptions, sessionOptions, signInViaApi, test } from './fixtures';
import { asUser, createUserViaApi } from './helpers';

/**
 * Own device listing, single device revocation, and revoking all other devices.
 */
test.describe.configure({ mode: 'serial' });

test('a user sees their devices and signs out another device', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'devices-own' });
	await adminApi.dispose();

	// First session
	const first = await asUser(browser, user);

	// Second session (sign in again to get a second active device)
	const secondSession = await signInViaApi(workerBaseURL, user.username, user.password);
	const secondContext = await browser.newContext(sessionOptions(workerBaseURL, secondSession));
	const secondPage = await secondContext.newPage();

	// In the first browser, go to account settings
	await first.page.goto('/settings/account');
	await expect(first.page.getByRole('heading', { name: 'Devices' })).toBeVisible();

	const deviceTable = first.page.getByRole('table', { name: 'Active devices' });
	const items = deviceTable.getByRole('row').filter({ has: first.page.getByRole('cell') });
	await expect(items).toHaveCount(2);

	// The current device is marked "This device" and has no Sign out button
	const currentItem = items.filter({ hasText: 'This device' });
	await expect(currentItem).toHaveCount(1);
	await expect(currentItem.getByRole('button', { name: 'Sign out' })).toHaveCount(0);

	// The other device has a Sign out button
	const otherItem = items.filter({ hasNotText: 'This device' });
	await expect(otherItem).toHaveCount(1);
	await otherItem.getByRole('button', { name: 'Sign out' }).click();

	await expect(first.page.getByText('Device signed out')).toBeVisible();
	await expect(items).toHaveCount(1);

	// The ended session on its next navigation or request is rejected and redirected to /login
	await secondPage.goto('/settings/account');
	await expect(secondPage).toHaveURL(/\/login/);

	await first.context.close();
	await secondContext.close();
});

test('a user can sign out all other devices at once', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'devices-others' });
	await adminApi.dispose();

	const first = await asUser(browser, user);

	const secondSession = await signInViaApi(workerBaseURL, user.username, user.password);
	const secondContext = await browser.newContext(sessionOptions(workerBaseURL, secondSession));
	const secondPage = await secondContext.newPage();

	const thirdSession = await signInViaApi(workerBaseURL, user.username, user.password);
	const thirdContext = await browser.newContext(sessionOptions(workerBaseURL, thirdSession));
	const thirdPage = await thirdContext.newPage();

	await first.page.goto('/settings/account');
	const items = first.page
		.getByRole('table', { name: 'Active devices' })
		.getByRole('row')
		.filter({ has: first.page.getByRole('cell') });
	await expect(items).toHaveCount(3);

	await first.page.getByRole('button', { name: 'Sign out all other devices' }).click();
	await first.page.getByRole('button', { name: 'Sign out other devices' }).click();

	await expect(first.page.getByText('Other devices signed out')).toBeVisible();
	await expect(items).toHaveCount(1);

	await secondPage.goto('/settings/account');
	await expect(secondPage).toHaveURL(/\/login/);

	await thirdPage.goto('/settings/account');
	await expect(thirdPage).toHaveURL(/\/login/);

	await first.context.close();
	await secondContext.close();
	await thirdContext.close();
});

test('devices page ten at a time, and signing out the others works from any page', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	test.setTimeout(180_000);
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'devices-pages' });
	await adminApi.dispose();

	const first = await asUser(browser, user);
	// Eleven more sign-ins, each a device of its own: twelve in all, so a second page of two.
	for (let n = 0; n < 11; n++) {
		await signInViaApi(workerBaseURL, user.username, user.password);
	}

	const { page } = first;
	try {
		await page.goto('/settings/account');
		const table = page.getByRole('table', { name: 'Active devices' });
		const rows = table.getByRole('row').filter({ has: page.getByRole('cell') });
		const nav = page.getByRole('navigation', { name: 'Device pages' });
		const range = nav.getByTestId('page-range');

		await expect(range).toHaveText('1–10 of 12 devices');
		await expect(rows).toHaveCount(10);
		const shots = process.env.SHOTS_DIR;
		if (shots) {
			await table.scrollIntoViewIfNeeded();
			await page.screenshot({ path: `${shots}/devices-page-1.png` });
		}

		// A header sorts all twelve on the server, not only the page on screen.
		await table.getByRole('button', { name: 'First signed in' }).click();
		await expect(table.getByRole('columnheader', { name: 'First signed in' })).toHaveAttribute(
			'aria-sort',
			'ascending'
		);
		await expect(range).toHaveText('1–10 of 12 devices');

		await nav.getByRole('button', { name: 'Next' }).click();
		await expect(range).toHaveText('11–12 of 12 devices');
		await expect(rows).toHaveCount(2);
		if (shots) await page.screenshot({ path: `${shots}/devices-page-2.png` });

		// The button needs no list of every device: the count says there are others.
		await page.getByRole('button', { name: 'Sign out all other devices' }).click();
		await page.getByRole('button', { name: 'Sign out other devices' }).click();
		await expect(page.getByText('Other devices signed out')).toBeVisible();
		await expect(rows).toHaveCount(1);
		await expect(range).toHaveText('1 device');
		await expect(page.getByRole('button', { name: 'Sign out all other devices' })).toHaveCount(0);
	} finally {
		await first.context.close();
	}
});
