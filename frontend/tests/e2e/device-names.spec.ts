import { expect, request, apiSessionOptions, test, type Browser, type Page } from './fixtures';
import { createUserViaApi, uniqueName, type E2EUser } from './helpers';

/**
 * Naming devices: the prompt after signing in through the form, dismissing it, renaming from the
 * Account page, an administrator renaming a user's device, and the name on the Users page.
 */
test.describe.configure({ mode: 'serial' });

const prompt = (page: Page) => page.getByRole('dialog', { name: 'Name this device' });

// A browser with no cookies: the project's default is the signed-in administrator.
const signedOutContext = (browser: Browser, baseURL: string) =>
	browser.newContext({ baseURL, storageState: { cookies: [], origins: [] }, extraHTTPHeaders: {} });

// The row of the browser being used; the account may have other devices from setting it up.
const currentDevice = (page: Page) => page.getByRole('row').filter({ hasText: 'This device' });

async function signInThroughForm(page: Page, user: E2EUser) {
	await page.goto('/login');
	await page.getByLabel('Username').fill(user.username);
	await page.getByLabel('Password', { exact: true }).fill(user.password);
	await page.getByRole('button', { name: 'Sign in', exact: true }).click();
}

test('signing in on an unnamed browser offers to name it', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'name-prompt' });
	await adminApi.dispose();
	const name = uniqueName('Desk laptop');

	const context = await signedOutContext(browser, workerBaseURL);
	const page = await context.newPage();
	await signInThroughForm(page, user);

	await expect(prompt(page)).toBeVisible();
	// The field is empty, with the generated label as its placeholder.
	await expect(prompt(page).getByLabel('Device name')).toHaveValue('');
	await expect(prompt(page).getByLabel('Device name')).toHaveAttribute('placeholder', /.+/);
	await prompt(page).getByLabel('Device name').fill(name);
	await prompt(page).getByRole('button', { name: 'Save name' }).click();
	await expect(page.getByText('Device named')).toBeVisible();
	await expect(prompt(page)).toHaveCount(0);

	// The name leads, with the generated label muted beneath it.
	await page.goto('/settings/account');
	const here = currentDevice(page);
	await expect(here.getByTestId('device-title')).toHaveText(name);
	await expect(here.getByTestId('device-subtitle')).not.toBeEmpty();

	await context.close();
});

test('the prompt can be dismissed and the device named later', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const user = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'name-later' });
	await adminApi.dispose();
	const name = uniqueName('Phone');

	const context = await signedOutContext(browser, workerBaseURL);
	const page = await context.newPage();
	await signInThroughForm(page, user);

	await prompt(page).getByRole('button', { name: 'Not now' }).click();
	await expect(prompt(page)).toHaveCount(0);

	// Unnamed, so the generated label is the title and there is no subtitle.
	await page.goto('/settings/account');
	const here = currentDevice(page);
	await expect(here.getByTestId('device-title')).toBeVisible();
	await expect(here.getByTestId('device-subtitle')).toHaveCount(0);

	// The pencil beside the device names it, and a blank name clears it again.
	await here.getByRole('button', { name: 'Name device' }).click();
	await here.getByLabel('Device name').fill(name);
	await here.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(here.getByTestId('device-title')).toHaveText(name);

	await here.getByRole('button', { name: 'Rename device' }).click();
	await here.getByLabel('Device name').fill('');
	await here.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(here.getByTestId('device-subtitle')).toHaveCount(0);

	await context.close();
});

test('an administrator can rename a users device', async ({
	page,
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const member = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'name-admin' });
	await adminApi.dispose();
	const name = uniqueName('Gym tablet');

	const context = await signedOutContext(browser, workerBaseURL);
	const memberPage = await context.newPage();
	await signInThroughForm(memberPage, member);
	await memberPage.getByRole('button', { name: 'Not now' }).click();

	await page.goto('/admin/devices');
	const row = page.locator('tr, li').filter({ hasText: member.displayName }).first();
	await row.getByRole('button', { name: 'Name device' }).click();
	await row.getByLabel('Device name').fill(name);
	await row.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(page.getByText('Device named')).toBeVisible();
	await expect(row.getByTestId('device-title')).toHaveText(name);

	// The owner sees the administrator's name on their own devices page.
	await memberPage.goto('/settings/account');
	await expect(memberPage.getByTestId('device-title').filter({ hasText: name })).toHaveCount(1);

	await context.close();
});

test("a user's devices on the Users page show the name they gave it", async ({
	page,
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const member = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'name-users' });
	await adminApi.dispose();
	const name = uniqueName('Kitchen tablet');
	const renamed = uniqueName('Hall tablet');

	const context = await signedOutContext(browser, workerBaseURL);
	const memberPage = await context.newPage();
	await signInThroughForm(memberPage, member);
	await prompt(memberPage).getByLabel('Device name').fill(name);
	await prompt(memberPage).getByRole('button', { name: 'Save name' }).click();
	await expect(memberPage.getByText('Device named')).toBeVisible();

	await page.goto('/admin/users');
	const userRow = page
		.getByRole('table', { name: 'Users' })
		.getByRole('row')
		.filter({ hasText: member.username });
	await userRow.getByRole('button', { name: 'Devices' }).click();
	// The member also has an unnamed session from being created over the API.
	const card = page
		.getByRole('list', { name: 'User devices' })
		.getByRole('listitem')
		.filter({ has: page.getByTestId('device-title').getByText(name, { exact: true }) });
	await expect(card).toHaveCount(1);
	await expect(card.getByTestId('device-subtitle')).not.toBeEmpty();

	// It can be renamed from there too, as on the Devices page.
	await card.getByRole('button', { name: 'Rename device' }).click();
	const form = page.getByRole('list', { name: 'User devices' }).getByLabel('Device name');
	await form.fill(renamed);
	await page
		.getByRole('list', { name: 'User devices' })
		.getByRole('button', { name: 'Save', exact: true })
		.click();
	await expect(page.getByText('Device named')).toBeVisible();
	await expect(
		page
			.getByRole('list', { name: 'User devices' })
			.getByTestId('device-title')
			.getByText(renamed, { exact: true })
	).toBeVisible();

	await context.close();
});
