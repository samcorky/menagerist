import { expect, request, apiSessionOptions, test } from './fixtures';
import { asUser, createUserViaApi } from './helpers';

/**
 * Scheduled tasks: an administrator sees what runs in the background, starts a task by hand
 * and watches the worker carry it out. Every e2e backend has a worker beside it.
 */
test.describe.configure({ mode: 'serial' });

const TASK = 'Clear expired sign-ins';

test('an administrator starts a task and sees the worker finish it', async ({ page }) => {
	await page.goto('/admin');
	await page.locator('a[href="/admin/scheduled-tasks"]').click();
	await expect(page.getByRole('heading', { name: 'Scheduled tasks', exact: true })).toBeVisible();

	const card = page.locator('li').filter({
		has: page.getByRole('heading', { name: TASK, exact: true })
	});
	await expect(
		card.getByText('Removes sessions and access tokens that have expired.')
	).toBeVisible();

	await card.getByRole('button', { name: `Run ${TASK} now` }).click();
	await expect(
		page.getByText("Started. It will run as soon as it's this task's turn.")
	).toBeVisible();

	// The worker picks it up and finishes it; the page follows without a reload.
	await card.getByText('Recent runs', { exact: true }).click();
	const runs = card.getByRole('list', { name: `Recent runs of ${TASK}` });
	await expect(runs.getByText('Finished', { exact: true })).toBeVisible({ timeout: 30_000 });
	await expect(runs.getByRole('listitem')).toHaveCount(1);
	await expect(runs.getByText('Started by an administrator')).toBeVisible();

	// Nothing is left running, so the task can be started again.
	await expect(card.getByRole('button', { name: `Run ${TASK} now` })).toBeEnabled();

	// The finished run survives a reload.
	await page.reload();
	const reloaded = page.locator('li').filter({
		has: page.getByRole('heading', { name: TASK, exact: true })
	});
	await reloaded.getByText('Recent runs', { exact: true }).click();
	await expect(
		reloaded
			.getByRole('list', { name: `Recent runs of ${TASK}` })
			.getByText('Finished', { exact: true })
	).toBeVisible();
});

test('a task that is only ever scheduled has no Run now', async ({ page }) => {
	await page.goto('/admin/scheduled-tasks');
	const card = page.locator('li').filter({
		has: page.getByRole('heading', { name: 'Permanently remove old deleted items', exact: true })
	});
	await expect(card).toBeVisible();
	await expect(card.getByText('Not scheduled', { exact: true })).toBeVisible();
	await expect(card.getByRole('button', { name: /Run .* now/ })).toHaveCount(0);
});

test('the page keeps internal wording out of sight', async ({ page }) => {
	await page.goto('/admin/scheduled-tasks');
	await expect(page.getByRole('heading', { name: 'Scheduled tasks', exact: true })).toBeVisible();
	await expect(page.getByText('backup.create')).toHaveCount(0);
	await expect(page.getByText(/\bworker\b/i)).toHaveCount(0);
	await expect(page.getByText(/\bcron\b/i)).toHaveCount(0);
});

test('a member cannot see or reach scheduled tasks', async ({
	browser,
	workerBaseURL,
	workerSession
}) => {
	const adminApi = await request.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const member = await createUserViaApi(adminApi, workerBaseURL, { prefix: 'tasks-member' });
	await adminApi.dispose();

	const memberSession = await asUser(browser, member);
	await memberSession.page.goto('/admin');
	await expect(memberSession.page.locator('a[href="/admin/scheduled-tasks"]')).toHaveCount(0);

	await memberSession.page.goto('/admin/scheduled-tasks');
	await expect(
		memberSession.page.getByText('Only administrators can access this area.')
	).toBeVisible();
	await memberSession.context.close();
});
