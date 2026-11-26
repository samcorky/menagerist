import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** Limit which item types a connection type can join (#744). */
test.describe.configure({ mode: 'serial' });

const { makeItem, makeItemType, cleanUp } = ownedData();
const edgeTypeIds: string[] = [];
const ownTypeIds: string[] = [];

test.afterEach(async ({ request }) => {
	for (const id of edgeTypeIds.splice(0)) await request.delete(`/api/v1/edge-types/${id}`);
	await cleanUp(request);
	// Subtypes first: a parent with subtypes cannot be deleted.
	for (const id of ownTypeIds.splice(0).reverse()) await request.delete(`/api/v1/node-types/${id}`);
});

async function makeType(
	request: import('@playwright/test').APIRequestContext,
	label: string,
	parent?: string
) {
	const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
	const res = await request.post('/api/v1/node-types', { data: { slug, label, parent } });
	expect(res.status(), await res.text()).toBe(201);
	const created = (await res.json()) as { id: string };
	ownTypeIds.push(created.id);
	return { slug, label };
}

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
		// The list is gone before the next one opens: two search boxes at once cannot be filled.
		await expect(page.getByPlaceholder('Search item types…')).toHaveCount(0);
	}

	// A chip can be removed again, and the list offers the type once more.
	await page.getByRole('button', { name: `Remove ${bookType.label}` }).click();
	await expect(page.getByRole('button', { name: `Remove ${bookType.label}` })).toHaveCount(0);
	await page.getByRole('combobox', { name: 'Starts from' }).click();
	await page.getByPlaceholder('Search item types…').fill(bookType.label);
	await page.getByRole('option', { name: bookType.label, exact: true }).click();
	await page.keyboard.press('Escape');
	await expect(page.getByPlaceholder('Search item types…')).toHaveCount(0);
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

test('a limit on a parent type covers its subtypes, and one on a subtype only that', async ({
	page,
	request
}) => {
	const stamp = uniqueName('Sub').replace(/\W+/g, '');
	const parent = await makeType(request, `${stamp} Memorabilia`);
	const poster = await makeType(request, `${stamp} Poster`, parent.slug);
	const figure = await makeType(request, `${stamp} Figure`, parent.slug);
	const box = await makeType(request, `${stamp} Box`);
	const crate = await makeItem(request, `${stamp} Crate`, box.slug);
	const stray = await makeItem(request, `${stamp} Stray box`, box.slug);
	const alien = await makeItem(request, `${stamp} Alien poster`, poster.slug);
	const statue = await makeItem(request, `${stamp} Statue`, figure.slug);

	const made = await request.post('/api/v1/edge-types', {
		data: {
			slug: `${stamp}-stored-in`.toLowerCase(),
			label: `${stamp} Stored in`,
			target_types: [parent.slug]
		}
	});
	expect(made.status(), await made.text()).toBe(201);
	const storedIn = (await made.json()) as { id: string; slug: string; label: string };
	edgeTypeIds.push(storedIn.id);

	// The picker offers items of the parent's subtypes, and not the box.
	await page.goto(`/items/${crate.id}`);
	await page.getByLabel('Connection').fill(storedIn.label);
	await page.getByRole('button', { name: storedIn.label }).click();
	await page.getByPlaceholder('Search items…').fill(stamp);
	await expect(page.getByRole('button', { name: new RegExp(alien.name) })).toBeVisible();
	await expect(page.getByRole('button', { name: new RegExp(statue.name) })).toBeVisible();
	await expect(page.getByRole('button', { name: new RegExp(stray.name) })).toHaveCount(0);

	// The server holds the same line: a poster is allowed, another box is not.
	const allowed = await request.post('/api/v1/edges', {
		data: { source_id: crate.id, target_id: alien.id, type: storedIn.slug }
	});
	expect(allowed.status(), await allowed.text()).toBe(201);
	const refused = await request.post('/api/v1/edges', {
		data: { source_id: crate.id, target_id: stray.id, type: storedIn.slug }
	});
	expect(refused.status()).toBe(400);

	// A limit on the poster subtype covers only posters, not its sibling.
	const narrowed = await request.patch(`/api/v1/edge-types/${storedIn.id}`, {
		data: { target_types: [poster.slug] }
	});
	expect(narrowed.ok()).toBeTruthy();
	const sibling = await request.post('/api/v1/edges', {
		data: { source_id: crate.id, target_id: statue.id, type: storedIn.slug }
	});
	expect(sibling.status()).toBe(400);
});
