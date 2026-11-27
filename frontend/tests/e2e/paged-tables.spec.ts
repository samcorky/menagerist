import { expect, request, apiSessionOptions, test } from './fixtures';
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
