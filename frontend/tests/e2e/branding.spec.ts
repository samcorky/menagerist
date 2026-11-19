import { expect, test, type Page } from './fixtures';

/**
 * Branding: an administrator names the instance on the settings page, and the installed
 * app's manifest (#117) and every page's link preview (#598) follow. Serial, as the tests
 * change the same instance settings.
 */
test.describe.configure({ mode: 'serial' });

// Each server process caches settings for up to five seconds; a save clears only the
// cache of the process that took it, so another may answer with the old value meanwhile.
const SETTLED = { timeout: 10_000 };

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
	await expect.poll(async () => (await manifest(page)).name, SETTLED).toBe('Menagerist');

	for (const [title, value] of [
		['App name', 'The Hoard'],
		['Short app name', 'Hoard'],
		['App description', "Our family's things."]
	] as const) {
		await page.getByLabel(title, { exact: true }).fill(value);
		await card(page, title).getByRole('button', { name: 'Save', exact: true }).click();
		await expect(card(page, title).getByText('Changed here', { exact: true })).toBeVisible();
	}

	await expect
		.poll(() => manifest(page), SETTLED)
		.toMatchObject({ name: 'The Hoard', short_name: 'Hoard', description: "Our family's things." });
});

test('a short name too long for a launcher is refused and nothing is saved', async ({ page }) => {
	await page.goto('/settings/server?section=branding');
	await page.getByLabel('Short app name', { exact: true }).fill('A much too long name');
	await card(page, 'Short app name').getByRole('button', { name: 'Save', exact: true }).click();

	await expect(card(page, 'Short app name').getByRole('alert')).toBeVisible();
	await expect.poll(async () => (await manifest(page)).short_name, SETTLED).toBe('Menagerist');
});

test("a pasted link's preview uses the instance's name and description", async ({ request }) => {
	for (const [key, value] of [
		['branding.name', 'The Hoard'],
		['branding.description', 'Our family & friends.']
	]) {
		const saved = await request.patch('/api/v1/settings/instance', {
			data: { values: { [key]: value } }
		});
		expect(saved.ok()).toBe(true);
	}

	const page = await (await request.get('/items/some-item')).text();

	expect(page).toContain('<meta property="og:title" content="The Hoard" />');
	expect(page).toContain('<meta property="og:site_name" content="The Hoard" />');
	expect(page).toMatch(/property="og:description"\s+content="Our family &amp; friends\."/);
	// The app's own name is not part of the preview, so it stays (#641).
	expect(page).toContain('<meta name="apple-mobile-web-app-title" content="Menagerist" />');
});
