import { expect, test } from './fixtures';

// Swagger UI's own assets come from the jsDelivr CDN.
const SWAGGER_ASSET = 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.0/swagger-ui-bundle.js';

test.beforeAll(async () => {
	let reachable: boolean;
	try {
		reachable = (await fetch(SWAGGER_ASSET, { signal: AbortSignal.timeout(8000) })).ok;
	} catch {
		reachable = false;
	}
	test.skip(!reachable, 'cdn.jsdelivr.net is unreachable, so Swagger UI cannot load.');
});

test('a response link opens the next operation with the id filled in', async ({ page }) => {
	await page.goto('/api/docs');
	await page.locator('.operation-filter-input').fill('Personal backups');
	const create = page.locator('.opblock[id$="-export_user_data"]');
	await expect(create).toBeVisible();
	if (!(await create.locator('.opblock-body').isVisible())) {
		await create.locator('.opblock-summary-control').click();
	}
	const tryItOut = create.getByRole('button', { name: 'Try it out' });
	if (await tryItOut.isVisible()) await tryItOut.click();
	await create.getByRole('button', { name: 'Execute' }).click();
	const live = create.locator('.live-responses-table .response');
	await expect(live.locator('.response-col_status').first()).toContainText('201', {
		timeout: 30_000
	});
	const id = (await create.locator('.live-responses-table .microlight').first().innerText()).match(
		/"id":\s*"([0-9a-f-]{36})"/
	)?.[1];
	expect(id).toBeTruthy();

	await create
		.locator('.responses-table:not(.live-responses-table) tr.response')
		.getByRole('button', { name: 'Open download_user_export' })
		.click();

	await page.waitForTimeout(1500);
	console.log(
		'DBG',
		page.url(),
		await page.locator('.opblock[id$="-download_user_export"]').count(),
		await page.locator('.opblock[id$="-download_user_export"]').getAttribute('class')
	);
	const target = page.locator('.opblock[id$="-download_user_export"]');
	await expect(target.locator('.opblock-body')).toBeVisible();
	await expect(target.getByRole('button', { name: 'Execute' })).toBeVisible();
	await expect(target.locator('input[placeholder="backup_id"]')).toHaveValue(id!);
});
