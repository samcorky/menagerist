import { expect, request, apiSessionOptions, test, type Page } from './fixtures';
import { asUser, createUserViaApi } from './helpers';

/**
 * A table, or one of several lists on a screen, pages with Previous and Next instead of
 * scrolling (design §19). The tokens on the Account page are the first to.
 */
test('personal access tokens page ten at a time, with where you are in the list', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	test.setTimeout(180_000);
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const member = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'token-pages' });
	await adminApi.dispose();
	const person = await asUser(browser, member);
	const { page } = person;
	try {
		// A new account, so the tokens are exactly these 15, newest first. (Twenty is the most a
		// person can hold, so the card never needs more than two pages of ten.)
		for (let n = 1; n <= 15; n++) {
			const created = await person.request.post('/api/v1/tokens', {
				data: {
					name: `Token ${String(n).padStart(2, '0')}`,
					password: member.password,
					grants: ['graph:type:read']
				}
			});
			expect(created.status(), await created.text()).toBe(201);
		}

		await page.goto('/settings/account');
		await expect(page.getByRole('heading', { name: 'Personal access tokens' })).toBeVisible();
		const nav = page.getByRole('navigation', { name: 'Token pages' });
		const range = nav.getByTestId('page-range');
		const previous = nav.getByRole('button', { name: 'Previous' });
		const next = nav.getByRole('button', { name: 'Next' });

		await expect(range).toHaveText('1–10 of 15 tokens');
		await expect(page.getByText('Token 15', { exact: true })).toBeVisible();
		await expect(page.getByText('Token 06', { exact: true })).toBeVisible();
		await expect(page.getByText('Token 05', { exact: true })).toHaveCount(0);
		await expect(previous).toBeDisabled();

		const shots = process.env.SHOTS_DIR;
		if (shots) await nav.scrollIntoViewIfNeeded();
		if (shots) await page.screenshot({ path: `${shots}/tokens-page-1.png` });

		await next.click();
		await expect(range).toHaveText('11–15 of 15 tokens');
		await expect(page.getByText('Token 05', { exact: true })).toBeVisible();
		await expect(page.getByText('Token 01', { exact: true })).toBeVisible();
		await expect(page.getByText('Token 15', { exact: true })).toHaveCount(0);
		await expect(next).toBeDisabled();
		await expect(previous).toBeEnabled();
		if (shots) await page.screenshot({ path: `${shots}/tokens-page-2.png` });

		await previous.click();
		await expect(range).toHaveText('1–10 of 15 tokens');
		await expect(page.getByText('Token 15', { exact: true })).toBeVisible();
	} finally {
		await person.context.close();
	}
});

test('a column header sorts the whole table on the server: up, down, then as it was', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	test.setTimeout(180_000);
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const member = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'token-sort' });
	await adminApi.dispose();
	const person = await asUser(browser, member);
	const { page } = person;
	try {
		// Made out of order, so the newest first, A to Z and Z to A all start with a different one.
		for (const n of [5, 12, 1, 9, 3, 11, 7, 2, 10, 6, 4, 8]) {
			const created = await person.request.post('/api/v1/tokens', {
				data: {
					name: `Token ${String(n).padStart(2, '0')}`,
					password: member.password,
					grants: ['graph:type:read']
				}
			});
			expect(created.status(), await created.text()).toBe(201);
		}

		await page.goto('/settings/account');
		const table = page.getByRole('table', { name: 'Personal access tokens' });
		const header = table.getByRole('columnheader', { name: 'Token' });
		const firstRow = table.getByRole('row').nth(1);
		const range = page.getByRole('navigation', { name: 'Token pages' }).getByTestId('page-range');

		// The server's own order: the last one made leads.
		await expect(firstRow).toContainText('Token 08');
		await expect(header).toHaveAttribute('aria-sort', 'none');

		await header.getByRole('button').click();
		await expect(header).toHaveAttribute('aria-sort', 'ascending');
		await expect(firstRow).toContainText('Token 01');
		await expect(range).toHaveText('1–10 of 12 tokens');

		const shots = process.env.SHOTS_DIR;
		if (shots) {
			await header.scrollIntoViewIfNeeded();
			await page.screenshot({ path: `${shots}/tokens-sorted.png` });
		}

		// The sort is of every token, not the ten on screen: the last two are on the next page.
		await page
			.getByRole('navigation', { name: 'Token pages' })
			.getByRole('button', { name: 'Next' })
			.click();
		await expect(range).toHaveText('11–12 of 12 tokens');
		await expect(firstRow).toContainText('Token 11');

		// Sorting again starts from the first page.
		await header.getByRole('button').click();
		await expect(header).toHaveAttribute('aria-sort', 'descending');
		await expect(range).toHaveText('1–10 of 12 tokens');
		await expect(firstRow).toContainText('Token 12');

		await header.getByRole('button').click();
		await expect(header).toHaveAttribute('aria-sort', 'none');
		await expect(firstRow).toContainText('Token 08');
	} finally {
		await person.context.close();
	}
});

/** Clicks a header twice and checks the list route was asked for each direction. */
async function headerAsksTheServer(page: Page, column: string, key: string) {
	const header = page.getByRole('columnheader', { name: column });
	await expect(header).toHaveAttribute('aria-sort', 'none');

	const asked = page.waitForRequest(
		(req) => req.url().includes(`sort=${key}`) && req.url().includes('order=asc')
	);
	await header.getByRole('button').click();
	await asked;
	await expect(header).toHaveAttribute('aria-sort', 'ascending');

	const reversed = page.waitForRequest(
		(req) => req.url().includes(`sort=${key}`) && req.url().includes('order=desc')
	);
	await header.getByRole('button').click();
	await reversed;
	await expect(header).toHaveAttribute('aria-sort', 'descending');
}

test('the Users table asks the server for the order a header names', async ({ page }) => {
	await page.goto('/admin/users');
	await headerAsksTheServer(page, 'Role', 'role');
});

test('the Backups table asks the server for the order a header names', async ({
	page,
	request
}) => {
	// Without a backup the page shows no table, so make one.
	const made = await request.post('/api/v1/backups', {
		data: { label: `sort-${Date.now()}` }
	});
	expect(made.status(), await made.text()).toBe(201);
	const { id } = (await made.json()) as { id: string };
	try {
		await page.goto('/admin/backups');
		await headerAsksTheServer(page, 'Size', 'size');
	} finally {
		await request.delete(`/api/v1/backups/${id}`);
	}
});
