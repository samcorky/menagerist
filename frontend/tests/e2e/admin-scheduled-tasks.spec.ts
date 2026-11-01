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
	await page.locator('main a[href="/admin/scheduled-tasks"]').click();
	await expect(page.getByRole('heading', { name: 'Scheduled tasks', exact: true })).toBeVisible();

	const table = page.getByRole('table', { name: 'Scheduled tasks' });
	const row = table.getByRole('row').filter({
		has: page.getByRole('rowheader', { name: TASK })
	});
	await expect(
		row.getByText('Removes sessions and access tokens that have expired.')
	).toBeVisible();

	await row.getByRole('button', { name: `Run ${TASK} now` }).click();
	await expect(
		page.getByText("Started. It will run as soon as it's this task's turn.")
	).toBeVisible();

	// The worker picks it up and finishes it; the page follows without a reload, and the
	// row's last run shows the outcome.
	await expect(row.getByText('Finished', { exact: true })).toBeVisible({ timeout: 30_000 });
	await row.getByRole('button', { name: `Recent runs of ${TASK}` }).click();
	const runs = page.getByRole('list', { name: `Recent runs of ${TASK}` });
	await expect(runs.getByRole('listitem')).toHaveCount(1);
	await expect(runs.getByText('Started by an administrator')).toBeVisible();

	// Nothing is left running, so the task can be started again.
	await expect(row.getByRole('button', { name: `Run ${TASK} now` })).toBeEnabled();

	// The finished run survives a reload.
	await page.reload();
	await expect(
		table
			.getByRole('row')
			.filter({ has: page.getByRole('rowheader', { name: TASK }) })
			.getByText('Finished', { exact: true })
	).toBeVisible();
});

test('an administrator changes a schedule from the table and puts it back', async ({ page }) => {
	await page.goto('/admin/scheduled-tasks');
	const table = page.getByRole('table', { name: 'Scheduled tasks' });
	const row = table.getByRole('row').filter({
		has: page.getByRole('rowheader', { name: TASK })
	});

	await row.getByRole('button', { name: `Change schedule of ${TASK}` }).click();
	await expect(page.getByRole('dialog', { name: 'Change schedule' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Save schedule' })).toBeDisabled();

	await page.getByRole('button', { name: 'Cron', exact: true }).click();
	await page.getByRole('textbox', { name: `Schedule for ${TASK}`, exact: true }).fill('17 4 * * *');
	await page.getByRole('button', { name: 'Save schedule' }).click();
	await expect(page.getByText('Schedule saved')).toBeVisible();
	await expect(row.getByText(/04:17/)).toBeVisible();

	// Putting it back to the default removes the override.
	await row.getByRole('button', { name: `Change schedule of ${TASK}` }).click();
	await page.getByRole('button', { name: 'Reset to default' }).click();
	await expect(page.getByText('Schedule reset to its default')).toBeVisible();
	await expect(row.getByText(/04:17/)).toHaveCount(0);
});

test('a heavy task asks before it runs and is never scheduled', async ({ page }) => {
	const heavy = 'Rebuild thumbnails';
	await page.goto('/admin/scheduled-tasks');
	const row = page
		.getByRole('table', { name: 'Scheduled tasks' })
		.getByRole('row')
		.filter({ has: page.getByRole('rowheader', { name: heavy }) });
	await expect(row.getByText('Only when started', { exact: true })).toBeVisible();
	await expect(row.getByRole('button', { name: `Change schedule of ${heavy}` })).toHaveCount(0);

	// Cancelling leaves it alone.
	await row.getByRole('button', { name: `Run ${heavy} now` }).click();
	const dialog = page.getByRole('dialog', { name: `Run "${heavy}" now?` });
	await expect(dialog).toBeVisible();
	await dialog.getByRole('button', { name: 'Cancel' }).click();
	await expect(dialog).toHaveCount(0);
	await expect(row.getByText('Never run', { exact: true })).toBeVisible();

	// Confirming starts it and the worker finishes it.
	await row.getByRole('button', { name: `Run ${heavy} now` }).click();
	await page
		.getByRole('dialog', { name: `Run "${heavy}" now?` })
		.getByRole('button', { name: 'Run now' })
		.click();
	await expect(row.getByText('Finished', { exact: true })).toBeVisible({ timeout: 30_000 });
});

test('a task that is only ever scheduled has no Run now', async ({ page }) => {
	await page.goto('/admin/scheduled-tasks');
	const row = page
		.getByRole('table', { name: 'Scheduled tasks' })
		.getByRole('row')
		.filter({
			has: page.getByRole('rowheader', { name: 'Permanently remove old deleted items' })
		});
	await expect(row).toBeVisible();
	await expect(row.getByText('Not scheduled', { exact: true })).toBeVisible();
	await expect(row.getByRole('button', { name: /Run .* now/ })).toHaveCount(0);
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
