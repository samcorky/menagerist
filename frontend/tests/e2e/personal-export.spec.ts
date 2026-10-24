import { expect, test } from './fixtures';

test('a user creates, lists and deletes a personal export', async ({ page }) => {
	await page.goto('/settings/account');
	const heading = page.getByRole('heading', { name: 'Your data' });
	await expect(heading).toBeVisible();

	const list = page.getByRole('list', { name: 'Exports' });
	// Clear any left over from earlier runs so the empty state is reachable.
	while ((await list.getByRole('listitem').count()) > 0) {
		await list.getByRole('button', { name: 'Delete' }).first().click();
		await page.getByRole('button', { name: 'Delete export' }).click();
		await expect(page.getByRole('button', { name: 'Delete export' })).toBeHidden();
	}
	await expect(page.getByText('No exports. They are kept for 24 hours.')).toBeVisible();

	await page.getByRole('button', { name: 'Create export' }).click();
	const rows = list.getByRole('listitem');
	await expect(rows).toHaveCount(1, { timeout: 30_000 });
	await expect(rows.first()).toContainText(/Expires in about 2[34] hours/);
	await expect(rows.first().getByRole('link', { name: 'Download' })).toHaveAttribute(
		'href',
		/\/api\/v1\/me\/export\/[^/]+\/download$/
	);

	await rows.first().getByRole('button', { name: 'Delete' }).click();
	await page.getByRole('button', { name: 'Delete export' }).click();
	await expect(page.getByText('No exports. They are kept for 24 hours.')).toBeVisible();
	await expect(rows).toHaveCount(0);
});
