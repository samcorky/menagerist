import { test, expect } from './fixtures';

test.use({ timezoneId: 'Europe/London', locale: 'en-GB' });

test.afterEach(async ({ request }) => {
	// The e2e account is shared: leave its preferences as they were found.
	for (const key of ['datetime.time_zone', 'datetime.date_order', 'datetime.clock']) {
		await request.delete(`/api/v1/me/settings/${key}`);
	}
});

test('time zone, date order and clock change how times read, and the server is told the zone', async ({
	page
}) => {
	await page.goto('/settings/preferences');
	const preview = page.getByText('Dates and times read like this:');
	await expect(preview).toBeVisible();
	await expect(preview).not.toContainText('GMT');

	// Time zone: search, pick, and the check line shows the time there.
	await page.getByRole('combobox', { name: 'Time zone' }).click();
	await page.getByPlaceholder('Search for a city or region…').fill('tokyo');
	await page.getByRole('option', { name: /Tokyo/ }).click();
	await expect(page.getByText('Saved').first()).toBeVisible();
	await expect(preview).toContainText('GMT+9');

	// Date order and clock: the preview reads month first, on a 24-hour clock.
	await page.getByRole('button', { name: 'Date format', exact: true }).click();
	await page.getByRole('option', { name: /^Month first/ }).click();
	await page.getByRole('button', { name: 'Clock', exact: true }).click();
	await page.getByRole('option', { name: /^24-hour/ }).click();
	await expect(preview).toContainText(/[A-Z][a-z]{2} \d{1,2}, \d{4}, \d{2}:\d{2} GMT\+9/);

	// After a reload the choices hold, and requests name the chosen zone for "today".
	await page.reload();
	await expect(preview).toContainText('GMT+9');
	// Item lists resolve relative dates, so they carry it; they run once the account is known.
	const zones: string[] = [];
	await page.route(/\/api\/v1\/nodes(\?|$)/, async (route) => {
		zones.push(route.request().headers()['time-zone'] ?? '');
		await route.continue();
	});
	await page.goto('/items');
	await expect.poll(() => zones.length).toBeGreaterThan(0);
	expect(new Set(zones)).toEqual(new Set(['Asia/Tokyo']));
});

test('saved choices show in the picker and the preview', async ({ page, request }) => {
	await request.patch('/api/v1/me/settings', {
		data: { values: { 'datetime.time_zone': 'Pacific/Kiritimati', 'datetime.date_order': 'ymd' } }
	});
	await page.goto('/settings/preferences');
	await expect(page.getByText('Dates and times read like this:')).toContainText(
		/\d{4}-\d{2}-\d{2}/
	);
	await expect(page.getByRole('combobox', { name: 'Time zone' })).toContainText('Kiritimati');
});
