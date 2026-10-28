import { expect, request, apiSessionOptions, test } from './fixtures';
import { asUser, createUserViaApi } from './helpers';

/**
 * Scheduled tasks: an administrator sees what runs in the background and starts a task by
 * hand. The e2e backend has no worker, so a started run stays waiting for its turn.
 */
test.describe.configure({ mode: 'serial' });

test('an administrator starts a task and sees it waiting, once, in its history', async ({
	page
}) => {
	await page.goto('/admin');
	await page.locator('a[href="/admin/scheduled-tasks"]').click();
	await expect(page.getByRole('heading', { name: 'Scheduled tasks', exact: true })).toBeVisible();

	const card = page.locator('li').filter({
		has: page.getByRole('heading', { name: 'Back up everything', exact: true })
	});
	await expect(card.getByText('Saves a full copy', { exact: false })).toBeVisible();

	await card.getByRole('button', { name: 'Run Back up everything now' }).click();
	await expect(
		page.getByText("Started. It will run as soon as it's this task's turn.")
	).toBeVisible();
	await expect(card.getByText('Waiting for a turn', { exact: true })).toBeVisible();

	// A task already in progress cannot be stacked.
	const button = card.getByRole('button', { name: 'Run Back up everything now' });
	await expect(button).toBeDisabled();
	await expect(button).toHaveText(/Waiting/);

	await card.getByText('Recent runs', { exact: true }).click();
	const runs = card.getByRole('list', { name: 'Recent runs of Back up everything' });
	await expect(runs.getByRole('listitem')).toHaveCount(1);
	await expect(runs.getByText('Waiting for a turn')).toBeVisible();
	await expect(runs.getByText('Started by an administrator')).toBeVisible();

	// The waiting run survives a reload.
	await page.reload();
	await expect(
		page
			.locator('li')
			.filter({ has: page.getByRole('heading', { name: 'Back up everything', exact: true }) })
			.getByText('Waiting for a turn', { exact: true })
	).toBeVisible();
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
