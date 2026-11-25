import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** Limit which item types a connection type can join (#744). */
test.describe.configure({ mode: 'serial' });

const { makeItem, makeItemType, cleanUp } = ownedData();
const edgeTypeIds: string[] = [];

test.afterEach(async ({ request }) => {
	for (const id of edgeTypeIds.splice(0)) await request.delete(`/api/v1/edge-types/${id}`);
	await cleanUp(request);
});

test('limits a connection type in the editor and offers only fitting items', async ({
	page,
	request
}) => {
	const stamp = uniqueName('Lim').replace(/\W+/g, '');
	const bookType = await makeItemType(request, `${stamp} Book`);
	const personType = await makeItemType(request, `${stamp} Person`);
	const book = await makeItem(request, `${stamp} Novel`, bookType.slug);
	const author = await makeItem(request, `${stamp} Author`, personType.slug);
	const other = await makeItem(request, `${stamp} Other Book`, bookType.slug);

	const label = `${stamp} Signed by`;
	await page.goto('/library/connection-types');
	await page.getByRole('button', { name: 'New relationship type' }).click();
	await page.getByLabel('Label', { exact: true }).fill(label);
	// Search for each item type and pick it; the choice shows as a chip.
	for (const [end, itemType] of [
		['Starts from', bookType],
		['Points to', personType]
	] as const) {
		await page.getByRole('combobox', { name: end }).click();
		await page.getByPlaceholder('Search item types…').fill(itemType.label);
		await page.getByRole('option', { name: itemType.label, exact: true }).click();
		await page.keyboard.press('Escape');
		await expect(page.getByRole('button', { name: `Remove ${itemType.label}` })).toBeVisible();
	}

	// A chip can be removed again, and the list offers the type once more.
	await page.getByRole('button', { name: `Remove ${bookType.label}` }).click();
	await expect(page.getByRole('button', { name: `Remove ${bookType.label}` })).toHaveCount(0);
	await page.getByRole('combobox', { name: 'Starts from' }).click();
	await page.getByPlaceholder('Search item types…').fill(bookType.label);
	await page.getByRole('option', { name: bookType.label, exact: true }).click();
	await page.keyboard.press('Escape');
	await page.getByRole('button', { name: 'Add relationship type' }).click();
	await expect(page.getByText('Connection type created')).toBeVisible();
	await expect(page.getByText(`Joins ${bookType.label} → ${personType.label}`)).toBeVisible();

	const types = await (await request.get('/api/v1/edge-types?limit=100')).json();
	const created = types.find((t: { label: string }) => t.label === label);
	edgeTypeIds.push(created.id);

	await page.goto(`/items/${book.id}`);
	await page.getByLabel('Connection').fill(label);
	await page.getByRole('button', { name: label }).click();
	const search = page.getByPlaceholder('Search items…');
	await search.fill(stamp);
	await expect(page.getByRole('button', { name: new RegExp(author.name) })).toBeVisible();
	await expect(page.getByRole('button', { name: new RegExp(other.name) })).toHaveCount(0);

	// The server holds the same line.
	const refused = await request.post('/api/v1/edges', {
		data: { source_id: book.id, target_id: other.id, type: created.slug }
	});
	expect(refused.status()).toBe(400);
	expect(await refused.text()).toContain(`joins only ${personType.slug} at its target`);
});
