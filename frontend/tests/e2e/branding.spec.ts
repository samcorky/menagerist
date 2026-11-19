import { expect, test, type Page } from './fixtures';

/**
 * Branding: an administrator names the instance on the settings page, and the installed
 * app's manifest follows (#117). Serial, as both tests change the same instance settings.
 */
test.describe.configure({ mode: 'serial' });

const card = (page: Page, title: string) =>
	page
		.getByRole('listitem')
		.filter({ has: page.getByRole('heading', { name: title, exact: true }) });

async function manifest(page: Page) {
	const response = await page.request.get('/manifest.webmanifest');
	expect(response.ok()).toBe(true);
	return (await response.json()) as { name: string; short_name: string; description: string };
}

test.afterEach(async ({ request }) => {
	for (const key of ['branding.name', 'branding.short_name', 'branding.description']) {
		const reset = await request.delete(`/api/v1/settings/instance/${key}`);
		expect(reset.ok(), `reset ${key}`).toBe(true);
	}
});

test('naming the instance renames the installed app', async ({ page }) => {
	await page.goto('/settings/server?section=branding');
	await expect(page.getByRole('heading', { name: 'Branding', exact: true })).toBeVisible();
	expect((await manifest(page)).name).toBe('Menagerist');

	for (const [title, value] of [
		['App name', 'The Hoard'],
		['Short app name', 'Hoard'],
		['App description', "Our family's things."]
	] as const) {
		await page.getByLabel(title, { exact: true }).fill(value);
		await card(page, title).getByRole('button', { name: 'Save', exact: true }).click();
		await expect(card(page, title).getByText('Changed here', { exact: true })).toBeVisible();
	}

	expect(await manifest(page)).toMatchObject({
		name: 'The Hoard',
		short_name: 'Hoard',
		description: "Our family's things."
	});
});

test('a short name too long for a launcher is refused and nothing is saved', async ({ page }) => {
	await page.goto('/settings/server?section=branding');
	await page.getByLabel('Short app name', { exact: true }).fill('A much too long name');
	await card(page, 'Short app name').getByRole('button', { name: 'Save', exact: true }).click();

	await expect(card(page, 'Short app name').getByRole('alert')).toBeVisible();
	expect((await manifest(page)).short_name).toBe('Menagerist');
});
