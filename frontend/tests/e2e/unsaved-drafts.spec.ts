import { test, expect, E2E_ADMIN, type BrowserContext, type Page } from './fixtures';
import { skipDeviceNamePrompt, uniqueName } from './helpers';

/** Make the server end this page's session: the next request answers 401. */
async function endSession(context: BrowserContext) {
	const cookies = (await context.cookies()).filter((c) => c.name === 'menagerist-session');
	expect(cookies).toHaveLength(1);
	await context.addCookies(cookies.map((c) => ({ ...c, value: 'not-a-real-session-token' })));
}

async function signInAgain(page: Page) {
	await expect(page).toHaveURL(/\/login\?next=/);
	await expect(page.getByTestId('session-expired')).toBeVisible();
	await page.getByLabel('Username').fill(E2E_ADMIN.username);
	await page.getByLabel('Password', { exact: true }).fill(E2E_ADMIN.password);
	await skipDeviceNamePrompt(page);
	await page.getByRole('button', { name: 'Sign in', exact: true }).click();
}

const restorePrompt = (page: Page) => page.getByTestId('draft-restore');

test('a new item typed in when the session ends is offered back after signing in', async ({
	page,
	context,
	request
}) => {
	const name = uniqueName('Draft lamp');
	await page.goto('/items/new');
	await page.getByLabel('Name').fill(name);
	await page.getByLabel('Description').fill('Brass, a little dented');

	await endSession(context);
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await signInAgain(page);

	await expect(page).toHaveURL(/\/items\/new$/);
	await expect(page.getByLabel('Name')).toHaveValue('');
	await restorePrompt(page).getByRole('button', { name: 'Restore' }).click();
	await expect(restorePrompt(page)).toBeHidden();
	await expect(page.getByLabel('Name')).toHaveValue(name);
	await expect(page.getByLabel('Description')).toHaveValue('Brass, a little dented');

	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(page).toHaveURL(/\/items\/(?!new$)[^/]+$/);
	const id = page.url().split('/').pop()!;

	// Saved, so nothing is offered again.
	await page.goto('/items/new');
	await expect(page.getByLabel('Name')).toBeVisible();
	await expect(restorePrompt(page)).toBeHidden();
	await request.delete(`/api/v1/nodes/${id}`);
});

test('an item edit is offered back after signing in, and Discard forgets it', async ({
	page,
	context,
	request
}) => {
	const name = uniqueName('Draft clock');
	const created = await request.post('/api/v1/nodes', { data: { name } });
	const { id } = (await created.json()) as { id: string };

	await page.goto(`/items/${id}`);
	await page.getByRole('button', { name: 'Edit' }).first().click();
	await page.getByLabel('Name').fill(`${name} (restored)`);

	await endSession(context);
	await page.getByRole('button', { name: 'Save changes' }).click();
	await signInAgain(page);

	await expect(page).toHaveURL(new RegExp(`/items/${id}$`));
	await restorePrompt(page).getByRole('button', { name: 'Restore' }).click();
	await expect(page.getByLabel('Name')).toHaveValue(`${name} (restored)`);

	// A second ending, then Discard: the item keeps its saved name and nothing lingers.
	await endSession(context);
	await page.getByRole('button', { name: 'Save changes' }).click();
	await signInAgain(page);
	await restorePrompt(page).getByRole('button', { name: 'Discard' }).click();
	await expect(restorePrompt(page)).toBeHidden();
	await expect(
		page.getByTestId('item-main').getByText(name, { exact: true }).first()
	).toBeVisible();
	await page.reload();
	await expect(
		page.getByTestId('item-main').getByText(name, { exact: true }).first()
	).toBeVisible();
	await expect(restorePrompt(page)).toBeHidden();

	await request.delete(`/api/v1/nodes/${id}`);
});
