import { test, expect, type Page } from './fixtures';
import { chooseItemType, createItemType, uniqueName } from './helpers';

const FIRST_DAY = 'First day of the week';

/** The weekday heading the calendar puts first, in a date field's picker on a new item. */
async function firstCalendarColumn(page: Page, typeLabel: string): Promise<string> {
	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Alien'));
	await chooseItemType(page, typeLabel);
	await page.getByRole('button', { name: 'Released' }).click();
	const head = page.locator('[data-calendar-head-cell]').first();
	await expect(head).toBeVisible();
	return (await head.textContent())?.trim() ?? '';
}

test.afterEach(async ({ request }) => {
	// The e2e account is shared: leave the preference as it was found.
	await request.delete('/api/v1/me/settings/calendar.first_day');
});

test('choose the first day of the week: it saves, survives a reload, reaches calendars and resets', async ({
	page
}) => {
	const typeLabel = uniqueName('Film');
	await createItemType(page, { label: typeLabel, fields: [{ label: 'Released', kind: 'date' }] });

	await page.goto('/settings');
	await page
		.getByRole('main')
		.getByRole('link', { name: /Preferences/ })
		.click();
	await expect(page.getByRole('heading', { name: 'Preferences', level: 1 })).toBeVisible();
	const row = page.getByRole('listitem').filter({ hasText: FIRST_DAY });
	await expect(row.getByText('Default', { exact: true })).toBeVisible();

	await row.getByRole('button', { name: FIRST_DAY, exact: true }).click();
	await page.getByRole('option', { name: 'Sunday', exact: true }).click();
	await expect(page.getByText('Saved')).toBeVisible();

	await page.reload();
	await expect(row.getByText('Changed here')).toBeVisible();
	await expect(row.getByRole('button', { name: FIRST_DAY, exact: true })).toHaveText(/Sunday/);

	expect(await firstCalendarColumn(page, typeLabel)).toMatch(/^Su/);

	await page.goto('/settings/preferences');
	await row.getByRole('button', { name: `Reset ${FIRST_DAY} to the default` }).click();
	await expect(row.getByText('Default', { exact: true })).toBeVisible();
	await expect(row.getByRole('button', { name: FIRST_DAY, exact: true })).toHaveText(/Automatic/);
});

test('offline, the preferences stay in force but cannot be changed, and say why', async ({
	page,
	request
}) => {
	await request.patch('/api/v1/me/settings', {
		data: { values: { 'calendar.first_day': 'saturday' } }
	});
	await page.goto('/settings/preferences');
	const row = page.getByRole('listitem').filter({ hasText: FIRST_DAY });
	await expect(row.getByRole('button', { name: FIRST_DAY, exact: true })).toHaveText(/Saturday/);

	await page.context().setOffline(true);
	await expect(
		page.getByText("You're offline, so your preferences can't be changed now.")
	).toBeVisible();
	await expect(row.getByRole('button', { name: FIRST_DAY, exact: true })).toBeDisabled();
	await expect(
		row.getByRole('button', { name: `Reset ${FIRST_DAY} to the default` })
	).toBeDisabled();
	await expect(row.getByRole('button', { name: FIRST_DAY, exact: true })).toHaveText(/Saturday/);

	await page.context().setOffline(false);
	await expect(row.getByRole('button', { name: FIRST_DAY, exact: true })).toBeEnabled();
});
