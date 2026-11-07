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
	// Swagger UI renders the whole API spec, which takes tens of seconds on a busy machine.
	test.slow();
	// The whole API is rendered, as a reader has it, with only the backups group opened.
	await page.goto('/api/docs#/Personal%20backups');
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
	const target = page.locator('.opblock[id$="-download_user_export"]');
	await expect(target.locator('.opblock-body')).toBeVisible();
	await expect(target.getByRole('button', { name: 'Execute' })).toBeVisible();
	await expect(target.locator('input[placeholder="export_id"]')).toHaveValue(id!);
	// The opened operation is brought into view and takes focus, so a keyboard or screen-reader
	// user lands on it instead of having to find it by hand.
	await expect
		.poll(async () => Math.abs((await target.boundingBox())?.y ?? Infinity), { timeout: 5000 })
		.toBeLessThan(10);
	await expect(target.locator('.opblock-summary-control')).toBeFocused();
});

test('a response link scrolls to an operation Swagger UI has not rendered yet', async ({
	page
}) => {
	test.slow();
	// Swagger UI keeps only the operations near the viewport in the page, so from the first
	// operation of a long group the target below is not there until the page has scrolled.
	await page.goto('/api/docs#/Nodes');
	const create = page.locator('.opblock[id$="-create_node"]');
	await expect(create).toBeVisible({ timeout: 30_000 });
	if (!(await create.locator('.opblock-body').isVisible())) {
		await create.locator('.opblock-summary-control').click();
	}
	const tryItOut = create.getByRole('button', { name: 'Try it out' });
	if (await tryItOut.isVisible()) await tryItOut.click();
	const target = page.locator('.opblock[id$="-get_node"]');
	await expect(target).toHaveCount(0);
	await create.getByRole('button', { name: 'Execute' }).click();
	await expect(
		create.locator('.live-responses-table tr.response .response-col_status').first()
	).toContainText('201', { timeout: 30_000 });

	await create
		.locator('.responses-table:not(.live-responses-table) tr.response')
		.getByRole('button', { name: 'Open get_node' })
		.click();

	await expect(target.locator('.opblock-body')).toBeVisible({ timeout: 15_000 });
	await expect
		.poll(async () => Math.abs((await target.boundingBox())?.y ?? Infinity), { timeout: 15_000 })
		.toBeLessThan(10);
	await expect(target.locator('.opblock-summary-control')).toBeFocused();
});
