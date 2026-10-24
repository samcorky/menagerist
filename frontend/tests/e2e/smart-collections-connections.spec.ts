import { test, expect, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * Connection conditions in the Filters panel on the Items page. Each test makes its own
 * relationship and items; only connections of that relationship are asked about.
 */
test.describe.configure({ mode: 'serial' });

const { makeItem, cleanUp } = ownedData();
const edgeTypeIds: string[] = [];

test.afterEach(async ({ request }) => {
	for (const id of edgeTypeIds.splice(0)) await request.delete(`/api/v1/edge-type/${id}`);
	await cleanUp(request);
});

const filtersDialog = (page: Page) => page.getByRole('dialog', { name: 'Filters' });

/** Writes a screenshot when SHOTS_DIR is set (manual review only). */
async function shot(page: Page, file: string) {
	const dir = process.env.SHOTS_DIR;
	if (!dir) return;
	await page.waitForTimeout(400);
	await page.screenshot({ path: `${dir}/${file}.png` });
}

async function seed(request: Parameters<typeof makeItem>[0]) {
	const suffix = uniqueName('x').replace(/\W+/g, '');
	const label = `Directed by ${suffix}`;
	const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
	const res = await request.post('/api/v1/edge-type', {
		data: { slug, label, reverse_label: `Director of ${suffix}`, directional: true }
	});
	expect(res.status(), await res.text()).toBe(201);
	edgeTypeIds.push(((await res.json()) as { id: string }).id);
	const film = await makeItem(request, `Casablanca${suffix}`);
	const lonely = await makeItem(request, `Lonely${suffix}`);
	const director = await makeItem(request, `Curtiz${suffix}`);
	const edge = await request.post('/api/v1/edge', {
		data: { source_id: film.id, target_id: director.id, type: slug }
	});
	expect(edge.status(), await edge.text()).toBe(201);
	return { label, film, lonely, director, suffix };
}

async function addConnectionRow(page: Page) {
	const dialog = filtersDialog(page);
	await dialog.getByRole('combobox', { name: 'Condition 1, field' }).click();
	await page.getByPlaceholder('Search fields…').fill('Connection');
	await page.getByRole('option', { name: 'Connection', exact: true }).click();
	return dialog;
}

const link = (page: Page, name: string) => page.getByRole('link', { name: new RegExp(name) });

test('finds items by a connection, a linked item and a filter on the linked item', async ({
	page,
	request
}) => {
	const data = await seed(request);
	await page.goto('/items');
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	await page.getByRole('button', { name: /^Filters/ }).click();
	const dialog = await addConnectionRow(page);

	await dialog
		.getByLabel('Condition 1, relationship')
		.selectOption({ label: `${data.label} / Director of ${data.suffix}` });
	await shot(page, 'connection-desktop-row');
	await dialog.getByLabel('Condition 1, direction').selectOption({ label: 'From this item' });
	await expect(link(page, data.film.name)).toBeVisible();
	await expect(link(page, data.director.name)).toHaveCount(0);
	await expect(link(page, data.lonely.name)).toHaveCount(0);

	// A filter on the linked item narrows by the director's name.
	await dialog.getByRole('button', { name: 'Condition 1, filter the linked item' }).click();
	await expect(dialog.getByRole('combobox', { name: 'Condition 2, field' })).toBeVisible();
	await dialog.getByRole('combobox', { name: 'Condition 2, field' }).click();
	await page.getByPlaceholder('Search fields…').fill('Name');
	await page.getByRole('option', { name: 'Name', exact: true }).click();
	await dialog.getByLabel('Condition 2, value').fill('nobody');
	await expect(link(page, data.film.name)).toHaveCount(0);
	await dialog.getByLabel('Condition 2, value').fill(data.director.name);
	await dialog.getByLabel('Condition 2, operator').selectOption({ label: 'is' });
	await expect(link(page, data.film.name)).toBeVisible();
	await shot(page, 'connection-desktop-filter');

	// No connection kind inside the filter on the linked item.
	await dialog.getByRole('combobox', { name: 'Condition 2, field' }).click();
	await page.getByPlaceholder('Search fields…').fill('Connection');
	await expect(page.getByRole('option', { name: 'Connection', exact: true })).toHaveCount(0);
	await page.keyboard.press('Escape');

	// "Is connected to" picks an item by name.
	await dialog.getByLabel('Condition 1, operator').selectOption({ label: 'Is connected to' });
	await dialog.getByRole('combobox', { name: 'Condition 1, item' }).click();
	await page.getByPlaceholder('Search items…').fill(data.director.name);
	await page.getByRole('option', { name: new RegExp(data.director.name) }).click();
	await expect(link(page, data.film.name)).toBeVisible();
	await expect(link(page, data.lonely.name)).toHaveCount(0);
	await dialog.getByRole('button', { name: 'Done' }).click();
	await expect(
		page
			.getByRole('list', { name: 'Active filters' })
			.getByText(`Connected to ${data.director.name}`)
	).toBeVisible();

	// "Has no connection" lists items with none.
	await page.getByRole('button', { name: /^Filters/ }).click();
	await filtersDialog(page)
		.getByLabel('Condition 1, operator')
		.selectOption({ label: 'Has no connection' });
	await expect(link(page, data.lonely.name)).toBeVisible();
	await expect(link(page, data.film.name)).toHaveCount(0);
});

test('shows the connection builder on a phone in both colour schemes', async ({
	page,
	request
}) => {
	test.skip(!process.env.SHOTS_DIR, 'screenshots only');
	await seed(request);
	await page.setViewportSize({ width: 390, height: 844 });
	await page.goto('/items');
	await page.getByRole('button', { name: /^Filters/ }).click();
	const dialog = await addConnectionRow(page);
	await dialog.getByLabel('Condition 1, relationship').selectOption({ index: 1 });
	await dialog.getByRole('button', { name: 'Condition 1, filter the linked item' }).click();
	await shot(page, 'connection-phone-light');
	await page.emulateMedia({ colorScheme: 'dark' });
	await shot(page, 'connection-phone-dark');
	await page.setViewportSize({ width: 1280, height: 900 });
	await shot(page, 'connection-desktop-dark');
});
