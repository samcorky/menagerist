import { test, expect, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** The item type list and its editor on a phone: no overflow, no button tooltips, no scroll behind. */
const { makeItemType, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

async function setUp(page: Page, request: Parameters<typeof makeItemType>[0]) {
	const type = await makeItemType(request, uniqueName('Phone type'));
	await request.patch(`/api/v1/node-type/${type.id}`, { data: { icon: 'film', colour: 'red' } });
	await page.goto('/settings/item-types');
	return type;
}

const row = (page: Page, label: string) => page.getByRole('listitem').filter({ hasText: label });
const viewportWidth = (page: Page) => page.viewportSize()!.width;

test('the list row fits the screen, with its actions inside it', async ({ page, request }) => {
	const type = await setUp(page, request);
	const edit = row(page, type.label).getByRole('button', { name: 'Edit item type' });
	await expect(edit).toBeVisible();

	const box = (await edit.boundingBox())!;
	expect(box.x + box.width).toBeLessThanOrEqual(viewportWidth(page));
	expect(box.width).toBeGreaterThanOrEqual(44);
	expect(box.height).toBeGreaterThanOrEqual(44);
	const overflow = await page
		.locator('#main-scroll')
		.evaluate((el) => el.scrollWidth - el.clientWidth);
	expect(overflow).toBeLessThanOrEqual(0);
});

test('tapping a button does not pop up a tooltip', async ({ page, request }) => {
	const type = await setUp(page, request);
	await row(page, type.label).getByRole('button', { name: 'Edit item type' }).tap();
	await expect(page.getByRole('dialog', { name: 'Edit item type' })).toBeVisible();
	await expect(page.locator('[data-slot="tooltip-content"]')).toHaveCount(0);
});

test('the editor fits the screen and does not scroll sideways', async ({ page, request }) => {
	const type = await setUp(page, request);
	await row(page, type.label).getByRole('button', { name: 'Edit item type' }).tap();
	const dialog = page.getByRole('dialog', { name: 'Edit item type' });
	await expect(dialog).toBeVisible();

	const { scroll, client } = await dialog.evaluate((el) => ({
		scroll: el.scrollWidth,
		client: el.clientWidth
	}));
	expect(scroll).toBeLessThanOrEqual(client);
	const box = (await dialog.boundingBox())!;
	expect(box.x).toBeGreaterThanOrEqual(0);
	expect(box.x + box.width).toBeLessThanOrEqual(viewportWidth(page));
});

test('the icon picker opens inside the editor, in reach of the keyboard', async ({
	page,
	request
}) => {
	const type = await setUp(page, request);
	await row(page, type.label).getByRole('button', { name: 'Edit item type' }).tap();
	const dialog = page.getByRole('dialog', { name: 'Edit item type' });
	await dialog.getByRole('button', { name: 'Choose icon' }).tap();

	const search = dialog.getByPlaceholder('Search icons…');
	await expect(search).toBeVisible();
	await expect(dialog.locator('[data-slot="icon-grid"] button').first()).toBeVisible();

	await search.fill('vinyl');
	await dialog.getByRole('button', { name: 'disc-3', exact: true }).tap();
	await expect(search).toHaveCount(0);
	await expect(
		dialog.getByTestId('type-appearance-preview').locator('[data-slot="type-icon"]')
	).toHaveAttribute('data-icon', 'disc-3');
});

test('the page behind a dialog cannot scroll while it is open', async ({ page, request }) => {
	const type = await setUp(page, request);
	const scroller = page.locator('#main-scroll');
	await expect(scroller).toHaveCSS('overflow-y', 'auto');

	await row(page, type.label).getByRole('button', { name: 'Edit item type' }).tap();
	await expect(page.getByRole('dialog', { name: 'Edit item type' })).toBeVisible();
	await expect(scroller).toHaveCSS('overflow-y', 'hidden');

	await page.getByRole('button', { name: 'Close' }).tap();
	await expect(scroller).toHaveCSS('overflow-y', 'auto');
});

test.describe('bottom bar and the keyboard', () => {
	const bar = (page: Page) => page.locator('nav[style*="site-nav"]');

	test('is hidden while a text field has focus, and back when it does not', async ({ page }) => {
		// The new item form focuses its Name field, so the keyboard is up on arrival.
		await page.goto('/items/new');
		await expect(bar(page)).toHaveCSS('height', '0px');

		await page.getByLabel('Name').blur();
		await expect(bar(page)).not.toHaveCSS('height', '0px');

		await page.getByLabel('Name').tap();
		await expect(bar(page)).toHaveCSS('height', '0px');
	});

	test('stays when a button, not a field, has focus', async ({ page }) => {
		await page.goto('/');
		await bar(page).getByRole('link', { name: 'Items' }).focus();
		await expect(bar(page)).not.toHaveCSS('height', '0px');
	});
});
