import { readFile } from 'node:fs/promises';
import { expect, test } from './fixtures';
import { asUser, createUserViaApi, uniqueName } from './helpers';

test('an administrator creates, verifies, downloads, uploads and deletes a backup', async ({
	page,
	request,
	isMobile
}) => {
	const label = uniqueName('Manual backup');
	const ids: string[] = [];
	try {
		await page.goto('/admin');
		await page.getByRole('link', { name: /Backups/ }).click();
		await expect(page.getByRole('heading', { name: 'Backups', exact: true })).toBeVisible();
		await expect(page.getByLabel('Backup label')).toHaveCount(0);
		await page.getByRole('button', { name: 'Create backup', exact: true }).click();
		await page.getByLabel('Backup label').fill(label);
		const created = page.waitForResponse(
			(res) => res.url().endsWith('/api/v1/backup') && res.request().method() === 'POST'
		);
		await page
			.getByRole('dialog')
			.getByRole('button', { name: 'Create backup', exact: true })
			.click();
		const archive = await (await created).json();
		ids.push(archive.id);
		// A table on desktop, a list of cards on a phone.
		const row = page
			.getByRole('table', { name: 'Backups', exact: true })
			.getByRole('row')
			.or(page.getByRole('list', { name: 'Backups', exact: true }).getByRole('listitem'))
			.filter({ hasText: label });
		await expect(row).toBeVisible();
		await row.getByRole('button', { name: 'Verify', exact: true }).click();
		await expect(row.getByRole('status', { name: 'Backup verified' })).toBeVisible();

		if (isMobile) {
			const overflow = await page.evaluate(
				() => document.documentElement.scrollWidth - document.documentElement.clientWidth
			);
			expect(overflow).toBeLessThanOrEqual(0);
			for (const name of ['Verify', 'Delete']) {
				const box = await row.getByRole('button', { name, exact: true }).boundingBox();
				expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
			}
		}

		const downloadEvent = page.waitForEvent('download');
		await row.getByRole('link', { name: 'Download', exact: true }).click();
		const download = await downloadEvent;
		const slug = label
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/^-|-$/g, '');
		expect(download.suggestedFilename()).toBe(
			`menagerist-${slug}-${archive.created_at.slice(0, 10)}-${archive.id}.tar.gz`
		);
		const path = await download.path();
		expect(path).toBeTruthy();
		const bytes = await readFile(path!);
		expect([...bytes.subarray(0, 2)]).toEqual([0x1f, 0x8b]);

		await page.getByRole('button', { name: 'Upload backup', exact: true }).click();
		await page.getByLabel('Backup archive').setInputFiles({
			name: 'backup.tar.gz',
			mimeType: 'application/gzip',
			buffer: bytes
		});
		const uploaded = page.waitForResponse(
			(res) => res.url().endsWith('/api/v1/backup/upload') && res.request().method() === 'POST'
		);
		await page
			.getByRole('dialog')
			.getByRole('button', { name: 'Upload backup', exact: true })
			.click();
		ids.push((await (await uploaded).json()).id);
		await expect(row).toHaveCount(2);

		const first = row.first();
		await first.getByRole('button', { name: 'Delete', exact: true }).click();
		await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click();
		await expect(row).toHaveCount(2);
		await first.getByRole('button', { name: 'Delete', exact: true }).click();
		await page
			.getByRole('dialog')
			.getByRole('button', { name: 'Delete backup', exact: true })
			.click();
		await expect(row).toHaveCount(1);
		await expect(page.getByRole('button', { name: 'Create backup', exact: true })).toBeFocused();
	} finally {
		for (const id of ids) await request.delete(`/api/v1/backup/${id}`);
	}
});

test('backup list failures can be retried and damaged uploads report an error', async ({
	page
}) => {
	await page.route('**/api/v1/backup', (route) =>
		route.fulfill({
			status: 503,
			contentType: 'application/problem+json',
			body: JSON.stringify({ detail: 'Unavailable' })
		})
	);
	await page.goto('/admin/backups');
	await expect(page.getByRole('alert')).toBeVisible();
	await page.unroute('**/api/v1/backup');
	await page.getByRole('button', { name: /Retry|Try again/ }).click();
	await expect(page.getByRole('alert')).toHaveCount(0);
	await page.getByRole('button', { name: 'Upload backup', exact: true }).click();
	await page.getByLabel('Backup archive').setInputFiles({
		name: 'damaged.tar.gz',
		mimeType: 'application/gzip',
		buffer: Buffer.from('damaged')
	});
	await page
		.getByRole('dialog')
		.getByRole('button', { name: 'Upload backup', exact: true })
		.click();
	await expect(page.getByRole('alert')).toBeVisible();
});

test('members cannot see backup controls or request the archive list', async ({
	page,
	browser,
	request,
	workerBaseURL
}) => {
	const member = await createUserViaApi(request, workerBaseURL, { prefix: 'backup-member' });
	const session = await asUser(browser, member);
	const archiveRequests: string[] = [];
	session.page.on('request', (req) => {
		if (new URL(req.url()).pathname.startsWith('/api/v1/backup')) archiveRequests.push(req.url());
	});
	try {
		await session.page.goto('/admin/backups');
		await expect(session.page.getByText('Only administrators can manage backups.')).toBeVisible();
		await expect(session.page.getByRole('button', { name: 'Create backup' })).toHaveCount(0);
		expect(archiveRequests).toEqual([]);
		await page.goto('/admin/backups');
		await expect(page.getByRole('heading', { name: 'Backups', exact: true })).toBeVisible();
	} finally {
		await session.context.close();
	}
});
