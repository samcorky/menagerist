import {
	test,
	expect,
	request as playwrightRequest,
	apiSessionOptions,
	type APIRequestContext,
	type Locator,
	type Page
} from './fixtures';
import { asUser, createUserViaApi, ownedData, uniqueName } from './helpers';

/**
 * Smart collections: saving a search, the collection page, editing, narrowing, slugs and the
 * exact count. The database is shared, so every test makes its own item type (a saved search
 * names a type and a field, so it only ever matches that type's items) and removes what it made.
 */
test.describe.configure({ mode: 'serial' });

const { makeCollection, makeItemType, trackCollection, trackCollectionFromUrl, cleanUp } =
	ownedData();

// Items are tracked here so they go before their type does.
const seededItemIds: string[] = [];

test.afterEach(async ({ request }) => {
	for (const id of seededItemIds.splice(0)) await request.delete(`/api/v1/node/${id}`);
	await cleanUp(request);
});

type Tool = { id: string; slug: string; label: string };
type Smart = { id: string; slug: string; name: string };

const WEIGHT = {
	type: 'object',
	properties: { weight: { title: 'Weight', type: 'number' } }
};

/** An item type with a number field "Weight". */
async function makeTool(request: APIRequestContext): Promise<Tool> {
	const tool = await makeItemType(request, uniqueName('Tool'));
	const res = await request.patch(`/api/v1/node-type/${tool.id}`, {
		data: { attributes_schema: WEIGHT }
	});
	expect(res.ok(), await res.text()).toBeTruthy();
	return tool;
}

async function makeToolItem(
	request: APIRequestContext,
	tool: Tool,
	name: string,
	attributes: Record<string, unknown> = {}
) {
	const res = await request.post('/api/v1/node', { data: { name, type: tool.slug, attributes } });
	expect(res.status(), await res.text()).toBe(201);
	const created = (await res.json()) as { id: string };
	seededItemIds.push(created.id);
	return created;
}

/** Seeds A (weight 2), B (5), C (8) and D (none); the names are unique to the call. */
async function seedItems(request: APIRequestContext, tool: Tool) {
	const suffix = uniqueName('x').replace(/\W+/g, '');
	const names = {
		a: `Anvil${suffix}`,
		b: `Bolt${suffix}`,
		c: `Chisel${suffix}`,
		d: `Drill${suffix}`
	};
	await makeToolItem(request, tool, names.a, { weight: 2 });
	await makeToolItem(request, tool, names.b, { weight: 5 });
	await makeToolItem(request, tool, names.c, { weight: 8 });
	await makeToolItem(request, tool, names.d);
	return { ...names, suffix };
}

/** The saved search "Weight is at least `min`" on the tool's items. */
function weightAtLeast(tool: Tool, min: number) {
	return {
		v: 1,
		where: {
			op: 'and',
			children: [{ kind: 'field', type: tool.slug, key: 'weight', op: '>=', value: min }]
		},
		sort: []
	};
}

/** Creates a smart collection through the API and tracks it for clean-up. */
async function makeSmart(
	request: APIRequestContext,
	name: string,
	definition: unknown
): Promise<Smart> {
	const res = await request.post('/api/v1/collection', { data: { name, definition } });
	expect(res.status(), await res.text()).toBe(201);
	const created = (await res.json()) as Smart;
	trackCollection(created.id);
	return created;
}

const itemLink = (page: Page, name: string) => page.getByRole('link', { name: new RegExp(name) });
const slugOf = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
const lastSegment = (page: Page) => new URL(page.url()).pathname.split('/').pop()!;

async function definitionOf(request: APIRequestContext, id: string): Promise<unknown> {
	const res = await request.get(`/api/v1/collection/${id}`);
	expect(res.ok(), await res.text()).toBeTruthy();
	return ((await res.json()) as { definition: unknown }).definition;
}

/** Picks a field in a row's searchable picker of the given dialog. */
async function pickField(page: Page, dialog: Locator, n: number, field: string) {
	const [group, label] = field.split(' › ');
	await dialog.getByRole('combobox', { name: `Condition ${n}, field` }).click();
	await page.getByPlaceholder('Search fields…').fill(`${group} ${label}`);
	await page.getByRole('option', { name: label, exact: true }).click();
	await expect(page.getByRole('listbox')).toHaveCount(0);
}

/** Fills a number-field condition row: the field, the operator and a value. */
async function fillRow(
	page: Page,
	dialog: Locator,
	n: number,
	row: { field: string; operator: string; value: string }
) {
	await pickField(page, dialog, n, row.field);
	await dialog.getByLabel(`Condition ${n}, operator`).selectOption({ label: row.operator });
	await dialog.getByLabel(`Condition ${n}, value`).fill(row.value);
}

const filtersDialog = (page: Page) => page.getByRole('dialog', { name: 'Filters' });
const conditionsDialog = (page: Page) => page.getByRole('dialog', { name: 'Edit conditions' });
const narrowedBar = (page: Page) => page.getByRole('region', { name: 'Narrowed view' });

/** Opens the ad-hoc Filter panel on a collection page and adds "Weight is at least `min`". */
async function narrowByWeight(page: Page, tool: Tool, min: string) {
	await page.getByRole('button', { name: /^Filter/ }).click();
	const dialog = filtersDialog(page);
	await expect(dialog).toBeVisible();
	await fillRow(page, dialog, 1, {
		field: `${tool.label} › Weight`,
		operator: 'is at least',
		value: min
	});
	await dialog.getByRole('button', { name: 'Done' }).click();
	await expect(dialog).toHaveCount(0);
}

// The first visit of each route is slower; keep it out of the real tests' timing.
test('warms up the routes', async ({ page, request }) => {
	test.setTimeout(120_000);
	const tool = await makeTool(request);
	const smart = await makeSmart(request, uniqueName('Warm'), weightAtLeast(tool, 1));
	for (const path of ['/collections', `/collections/${smart.slug}`, '/items']) {
		await page.goto(path, { waitUntil: 'networkidle' });
	}
});

test('saves an items-page filter as a smart collection, lists it, opens it and keeps it current', async ({
	page,
	request
}) => {
	const tool = await makeTool(request);
	const names = await seedItems(request, tool);
	const name = uniqueName('Heavy');

	await page.goto('/items');
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	await page.getByRole('button', { name: /^Filters/ }).click();
	const dialog = filtersDialog(page);
	await expect(dialog).toBeVisible();
	await fillRow(page, dialog, 1, {
		field: `${tool.label} › Weight`,
		operator: 'is at least',
		value: '5'
	});
	await dialog.getByRole('button', { name: 'Done' }).click();
	await expect(dialog).toHaveCount(0);

	// A server rejection of a condition shows inline in the save dialog, numbered.
	await page.getByRole('button', { name: 'Save as smart collection' }).click();
	const save = page.getByRole('dialog', { name: 'Save as smart collection' });
	await save.getByLabel('Name').fill(name);
	await page.route(/\/api\/v1\/collection$/, (route) =>
		route.request().method() === 'POST'
			? route.fulfill({
					status: 400,
					contentType: 'application/json',
					body: JSON.stringify({ detail: 'where.children[0]: That value is not valid here.' })
				})
			: route.continue()
	);
	await save.getByRole('button', { name: 'Save smart collection' }).click();
	await expect(save.getByRole('alert')).toHaveText('Condition 1: That value is not valid here.');
	await expect(save).toBeVisible();
	await page.unroute(/\/api\/v1\/collection$/);

	await save.getByRole('button', { name: 'Save smart collection' }).click();
	await page.waitForURL(/\/collections\/(?!$)[^/]+$/);
	trackCollectionFromUrl(page);

	// Saving lands on the collection, addressed by its slug.
	expect(lastSegment(page)).toBe(slugOf(name));
	await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
	await expect(page.getByText('Smart', { exact: true })).toBeVisible();
	await expect(page.getByText('Saved conditions')).toBeVisible();
	await expect(page.getByText('Items are added automatically by the conditions.')).toBeVisible();
	await expect(itemLink(page, names.b)).toBeVisible();
	await expect(itemLink(page, names.c)).toBeVisible();
	await expect(itemLink(page, names.a)).toHaveCount(0);
	await expect(itemLink(page, names.d)).toHaveCount(0);
	await expect(page.getByText('2 items', { exact: true })).toBeVisible();

	// Nothing can be added or removed by hand.
	await expect(page.getByRole('button', { name: /Add items/ })).toHaveCount(0);
	await expect(page.getByRole('button', { name: /Remove .* from this collection/ })).toHaveCount(0);

	// A new matching item appears on reload, and the count follows.
	const added = uniqueName('Late').replace(/\W+/g, '');
	await makeToolItem(request, tool, added, { weight: 9 });
	await page.reload();
	await expect(itemLink(page, added)).toBeVisible();
	await expect(page.getByText('3 items', { exact: true })).toBeVisible();

	// The list shows the badge and the live count, and links by slug.
	await page.goto('/collections');
	const card = page.getByRole('link', { name: new RegExp(name) });
	await expect(card).toBeVisible();
	await expect(card).toContainText('Smart');
	await expect(card).toContainText('3 items');
	await expect(card).toHaveAttribute('href', `/collections/${slugOf(name)}`);
});

test('Edit conditions: Cancel keeps the definition, Save changes the results', async ({
	page,
	request
}) => {
	const tool = await makeTool(request);
	const names = await seedItems(request, tool);
	const smart = await makeSmart(request, uniqueName('Editable'), weightAtLeast(tool, 5));
	const before = await definitionOf(request, smart.id);

	await page.goto(`/collections/${smart.slug}`);
	await expect(itemLink(page, names.b)).toBeVisible();
	await expect(itemLink(page, names.c)).toBeVisible();

	await page.getByRole('button', { name: 'Edit conditions' }).click();
	const dialog = conditionsDialog(page);
	await expect(dialog).toBeVisible();
	await dialog.getByLabel('Condition 1, value').fill('8');
	await dialog.getByRole('button', { name: 'Cancel' }).click();
	await expect(dialog).toHaveCount(0);

	// Nothing was saved, on the page or on the server.
	await expect(itemLink(page, names.b)).toBeVisible();
	expect(await definitionOf(request, smart.id)).toEqual(before);
	await page.reload();
	await expect(itemLink(page, names.b)).toBeVisible();

	await page.getByRole('button', { name: 'Edit conditions' }).click();
	await expect(dialog).toBeVisible();
	await dialog.getByLabel('Condition 1, value').fill('8');
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(page.getByText('Conditions saved')).toBeVisible();
	await expect(dialog).toHaveCount(0);

	await expect(itemLink(page, names.c)).toBeVisible();
	await expect(itemLink(page, names.b)).toHaveCount(0);
	await expect(page.getByText('1 item', { exact: true })).toBeVisible();
	expect(await definitionOf(request, smart.id)).not.toEqual(before);

	// A rename straight after a definition save must not be refused as a stale write.
	await page.getByRole('button', { name: 'Edit', exact: true }).click();
	const edit = page.getByRole('dialog', { name: 'Edit collection' });
	const renamed = uniqueName('Renamed');
	await edit.getByLabel('Name').fill(renamed);
	await edit.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(page.getByText('Collection saved')).toBeVisible();
	await expect(page.getByRole('heading', { name: renamed, level: 1 })).toBeVisible();
	await expect(edit).toHaveCount(0);
});

test('saves what the items page shows: the search text and the type as well as the filter', async ({
	page,
	request
}) => {
	const tool = await makeTool(request);
	const names = await seedItems(request, tool);
	const name = uniqueName('OnScreen');

	await page.goto(`/items?type=${tool.slug}`);
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	// Search text alone is enough to offer the button
	await page.getByPlaceholder('Search your items…').fill(names.suffix);
	await expect(page.getByRole('button', { name: 'Save as smart collection' })).toBeVisible();

	await page.getByRole('button', { name: /^Filters/ }).click();
	const dialog = filtersDialog(page);
	await fillRow(page, dialog, 1, {
		field: `${tool.label} › Weight`,
		operator: 'is at least',
		value: '5'
	});
	await dialog.getByRole('button', { name: 'Done' }).click();
	await expect(dialog).toHaveCount(0);

	await page.getByRole('button', { name: 'Save as smart collection' }).click();
	const save = page.getByRole('dialog', { name: 'Save as smart collection' });
	await save.getByLabel('Name').fill(name);
	await save.getByRole('button', { name: 'Save smart collection' }).click();
	await page.waitForURL(/\/collections\/(?!$)[^/]+$/);
	trackCollectionFromUrl(page);

	// Weight at least 5 would match B and C; the search text narrows it to the seeded ones.
	await expect(itemLink(page, names.b)).toBeVisible();
	await expect(itemLink(page, names.c)).toBeVisible();
	const res = await request.get(`/api/v1/collection/${lastSegment(page)}`);
	const saved = (await res.json()) as { definition: { where: { children: { kind: string }[] } } };
	const kinds = saved.definition.where.children.map((c) => c.kind).sort();
	expect(kinds).toEqual(['field', 'text', 'type']);
});

test('a condition on a removed field shows a warning, and the list still loads', async ({
	page,
	request
}) => {
	const tool = await makeTool(request);
	await seedItems(request, tool);
	const smart = await makeSmart(request, uniqueName('Stale'), weightAtLeast(tool, 5));

	const patched = await request.patch(`/api/v1/node-type/${tool.id}`, {
		data: { attributes_schema: { type: 'object', properties: {} } }
	});
	expect(patched.ok(), await patched.text()).toBeTruthy();

	await page.goto(`/collections/${smart.slug}`);
	await expect(page.getByRole('heading', { name: smart.name, level: 1 })).toBeVisible();
	await expect(page.getByText(/no longer exists|is archived/).first()).toBeVisible();
	await expect(page.getByRole('list', { name: 'Conditions' })).toBeVisible();
	await expect(page.getByText('No items match these conditions')).toBeVisible();

	// The Collections page counts it without an error.
	await page.goto('/collections');
	const card = page.getByRole('link', { name: new RegExp(smart.name) });
	await expect(card).toBeVisible();
	await expect(card).toContainText('No items');
});

test('smart collections are not offered as places to add an item, and links use the slug', async ({
	page,
	request
}) => {
	const tool = await makeTool(request);
	const names = await seedItems(request, tool);
	const smart = await makeSmart(request, uniqueName('Auto'), weightAtLeast(tool, 1));
	const manual = await makeCollection(request, uniqueName('Hand'));
	const manualSlug = (
		(await (await request.get(`/api/v1/collection/${manual.id}`)).json()) as Smart
	).slug;

	// Adding to or removing from a smart collection is refused by the API.
	const item = await makeToolItem(request, tool, uniqueName('Pick').replace(/\W+/g, ''), {
		weight: 3
	});
	expect(
		(
			await request.put(`/api/v1/collection/${smart.id}/item`, { data: { item_ids: [item.id] } })
		).status()
	).toBe(409);
	expect((await request.delete(`/api/v1/collection/${smart.id}/item/${item.id}`)).status()).toBe(
		409
	);
	await request.put(`/api/v1/collection/${manual.id}/item`, { data: { item_ids: [item.id] } });

	// On the item page the picker lists the manual collection only, and the chip links by slug.
	await page.goto(`/items/${item.id}`);
	const chip = page.getByRole('link', { name: manual.name });
	await expect(chip).toBeVisible();
	await expect(chip).toHaveAttribute('href', `/collections/${manualSlug}`);
	await expect(page.getByRole('link', { name: smart.name })).toHaveCount(0);
	await page.getByRole('button', { name: `Remove from ${manual.name}` }).click();
	await page.getByRole('button', { name: 'Add to collection' }).first().click();
	const picker = page.getByRole('dialog', { name: 'Add to collection' });
	await expect(picker.getByRole('button', { name: manual.name })).toBeVisible();
	await expect(picker.getByRole('button', { name: smart.name })).toHaveCount(0);
	await page.keyboard.press('Escape');

	// The search popup opens it by slug.
	await page.goto('/');
	await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
	await page.keyboard.press('/');
	const popup = page.getByRole('dialog', { name: 'Search', exact: true });
	await expect(popup).toBeVisible();
	await popup.getByPlaceholder('Search everything…').fill(smart.name);
	await popup.getByRole('option', { name: new RegExp(smart.name) }).click();
	await expect(page).toHaveURL(new RegExp(`/collections/${smart.slug}$`));
	await expect(page.getByRole('heading', { name: smart.name, level: 1 })).toBeVisible();
	await expect(itemLink(page, names.a)).toBeVisible();
});

test('another user cannot open a smart collection by id or by slug, nor count or list it', async ({
	browser,
	request,
	workerBaseURL,
	workerSession
}) => {
	const tool = await makeTool(request);
	await seedItems(request, tool);
	const smart = await makeSmart(request, uniqueName('Private'), weightAtLeast(tool, 1));

	const admin = await playwrightRequest.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const other = await createUserViaApi(admin, workerBaseURL, { prefix: 'smart-b' });
	await admin.dispose();
	const b = await asUser(browser, other);

	for (const segment of [smart.id, smart.slug]) {
		await b.page.goto(`/collections/${segment}`);
		await expect(b.page.getByRole('heading', { name: 'Collection not found' })).toBeVisible();
		await expect(b.page.getByText(smart.name)).toHaveCount(0);
		expect((await b.request.get(`/api/v1/collection/${segment}`)).status()).toBe(404);
		expect((await b.request.get(`/api/v1/collection/${segment}/count`)).status()).toBe(404);
	}
	expect((await b.request.get(`/api/v1/node?collection=${smart.id}`)).status()).toBe(404);
	await b.context.close();
});

test('narrows a smart collection with filters, the search box and a type, without editing it', async ({
	page,
	request
}) => {
	const tool = await makeTool(request);
	const names = await seedItems(request, tool);
	// Saved: weight at least 2 (A, B, C).
	const smart = await makeSmart(request, uniqueName('Narrow'), weightAtLeast(tool, 2));
	const saved = await definitionOf(request, smart.id);

	await page.goto(`/collections/${smart.id}`);
	// Opened by id, the address becomes the slug.
	await expect(page).toHaveURL(new RegExp(`/collections/${smart.slug}$`));
	await expect(itemLink(page, names.a)).toBeVisible();
	await expect(narrowedBar(page)).toHaveCount(0);

	await narrowByWeight(page, tool, '5');
	await expect(narrowedBar(page)).toContainText('Narrowed by 1 filter: 2 of 3 items');
	await expect(itemLink(page, names.a)).toHaveCount(0);
	await expect(page).toHaveURL(/[?&]f=/);

	await page.getByPlaceholder('Search this collection…').fill(names.b);
	await expect(narrowedBar(page)).toContainText('Narrowed by 2 filters: 1 of 3 items');
	await expect(itemLink(page, names.b)).toBeVisible();
	await expect(itemLink(page, names.c)).toHaveCount(0);
	await expect(page).toHaveURL(/[?&]q=/);

	await page.getByRole('combobox', { name: 'Item type' }).selectOption(tool.slug);
	await expect(narrowedBar(page)).toContainText('Narrowed by 3 filters: 1 of 3 items');
	await expect(page).toHaveURL(new RegExp(`[?&]type=${tool.slug}`));

	// The address carries the narrowing: a reload keeps it.
	await page.reload();
	await expect(narrowedBar(page)).toContainText('Narrowed by 3 filters: 1 of 3 items');
	await expect(itemLink(page, names.b)).toBeVisible();
	await expect(page.getByPlaceholder('Search this collection…')).toHaveValue(names.b);

	// The narrowing is one history entry: Back leaves it, Forward restores all of it.
	await page.goBack();
	await expect(page).toHaveURL(new RegExp(`/collections/${smart.slug}$`));
	await expect(narrowedBar(page)).toHaveCount(0);
	await expect(itemLink(page, names.a)).toBeVisible();
	await page.goForward();
	await expect(narrowedBar(page)).toContainText('Narrowed by 3 filters: 1 of 3 items');
	await expect(itemLink(page, names.b)).toBeVisible();

	// The saved definition has not moved.
	expect(await definitionOf(request, smart.id)).toEqual(saved);

	// Save as new: a second smart collection with the saved and the added conditions.
	await narrowedBar(page).getByRole('button', { name: 'Save as new smart collection' }).click();
	const save = page.getByRole('dialog', { name: 'Save as smart collection' });
	const copyName = uniqueName('Narrow copy');
	await save.getByLabel('Name').fill(copyName);
	await save.getByRole('button', { name: 'Save smart collection' }).click();
	await expect(page.getByRole('heading', { name: copyName, level: 1 })).toBeVisible();
	trackCollectionFromUrl(page);
	await expect(itemLink(page, names.b)).toBeVisible();
	await expect(itemLink(page, names.c)).toHaveCount(0);
	await expect(page.getByText('1 item', { exact: true })).toBeVisible();
	expect(await definitionOf(request, smart.id)).toEqual(saved);

	// Back on the original: Clear removes every narrowing.
	await page.goto(`/collections/${smart.slug}`);
	await narrowByWeight(page, tool, '5');
	await expect(narrowedBar(page)).toBeVisible();
	await narrowedBar(page).getByRole('button', { name: 'Clear' }).click();
	await expect(narrowedBar(page)).toHaveCount(0);
	await expect(page).not.toHaveURL(/[?&]f=/);
	await expect(itemLink(page, names.a)).toBeVisible();

	// Update this collection: Cancel in the confirmation changes nothing, confirming replaces.
	await narrowByWeight(page, tool, '5');
	await narrowedBar(page).getByRole('button', { name: 'Update this collection' }).click();
	const confirm = page.getByRole('alertdialog').or(page.getByRole('dialog', { name: /Update/ }));
	await expect(confirm).toBeVisible();
	await confirm.getByRole('button', { name: 'Cancel' }).click();
	await expect(confirm).toHaveCount(0);
	expect(await definitionOf(request, smart.id)).toEqual(saved);

	await narrowedBar(page).getByRole('button', { name: 'Update this collection' }).click();
	await confirm.getByRole('button', { name: 'Update collection' }).click();
	await expect(narrowedBar(page)).toHaveCount(0);
	await expect(itemLink(page, names.a)).toHaveCount(0);
	await expect(itemLink(page, names.b)).toBeVisible();
	expect(await definitionOf(request, smart.id)).not.toEqual(saved);
});

test('saving a narrowed view is blocked, with a reason, when the search text is too long', async ({
	page,
	request
}) => {
	const tool = await makeTool(request);
	await seedItems(request, tool);
	const smart = await makeSmart(request, uniqueName('Long'), weightAtLeast(tool, 1));

	await page.goto(`/collections/${smart.slug}`);
	await page.getByPlaceholder('Search this collection…').fill('x'.repeat(201));
	const bar = narrowedBar(page);
	await expect(bar).toBeVisible();
	await expect(bar.getByRole('button', { name: 'Save as new smart collection' })).toBeDisabled();
	await expect(bar.getByRole('button', { name: 'Update this collection' })).toBeDisabled();
	await expect(bar).toContainText('The search text is too long to save as a condition');
});

test('edits the slug: no history entry, old link gone, taken and invalid slugs refused, regenerate', async ({
	page,
	request
}) => {
	const tool = await makeTool(request);
	await seedItems(request, tool);
	const name = uniqueName('Slugged');
	const smart = await makeSmart(request, name, weightAtLeast(tool, 1));
	expect(smart.slug).toBe(slugOf(name));

	// Opened by id, the address is replaced by the slug and Back skips the id entry.
	await page.goto('/collections');
	await page.goto(`/collections/${smart.id}`);
	await expect(page).toHaveURL(new RegExp(`/collections/${smart.slug}$`));
	await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
	await page.goBack();
	await expect(page).toHaveURL(/\/collections$/);
	await page.goForward();
	await expect(page).toHaveURL(new RegExp(`/collections/${smart.slug}$`));

	const openEdit = async () => {
		await page.getByRole('button', { name: 'Edit', exact: true }).click();
		const dialog = page.getByRole('dialog', { name: 'Edit collection' });
		await expect(dialog).toBeVisible();
		return dialog;
	};

	// Rename the slug.
	const custom = slugOf(uniqueName('custom-link'));
	let dialog = await openEdit();
	await dialog.getByLabel('Slug').fill(custom);
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(page.getByText('Collection saved')).toBeVisible();
	await expect(page).toHaveURL(new RegExp(`/collections/${custom}$`));
	await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();

	// The old slug no longer resolves; the id still does.
	await page.goto(`/collections/${smart.slug}`);
	await expect(page.getByRole('heading', { name: 'Collection not found' })).toBeVisible();
	expect((await request.get(`/api/v1/collection/${smart.id}`)).status()).toBe(200);

	// A slug another collection holds is refused inline.
	const other = await makeCollection(request, uniqueName('Holder'));
	const otherSlug = ((await (await request.get(`/api/v1/collection/${other.id}`)).json()) as Smart)
		.slug;
	await page.goto(`/collections/${custom}`);
	dialog = await openEdit();
	await dialog.getByLabel('Slug').fill(otherSlug);
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(dialog.getByText('That link is already used by another collection.')).toBeVisible();

	// A UUID-shaped slug is refused inline too.
	await dialog.getByLabel('Slug').fill(smart.id);
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(dialog.locator('#edit-collection-slug-error')).toBeVisible();
	await expect(page).toHaveURL(new RegExp(`/collections/${custom}$`));
	await page.keyboard.press('Escape');
	await expect(dialog).toHaveCount(0);

	// Regenerate rebuilds from the name; a taken one gets a suffix.
	const rival = await makeCollection(request, name);
	expect(((await (await request.get(`/api/v1/collection/${rival.id}`)).json()) as Smart).slug).toBe(
		slugOf(name)
	);
	dialog = await openEdit();
	await dialog.getByRole('button', { name: 'Regenerate from name' }).click();
	await expect(page).toHaveURL(new RegExp(`/collections/${slugOf(name)}-2$`));
	await expect(dialog.getByLabel('Slug')).toHaveValue(`${slugOf(name)}-2`);
	await page.keyboard.press('Escape');
});

test('shows 1,000+ for a capped count, then the exact figure; a failed count offers a retry', async ({
	page,
	request
}) => {
	const tool = await makeTool(request);
	await seedItems(request, tool);
	const smart = await makeSmart(request, uniqueName('Capped'), weightAtLeast(tool, 1));

	// Make the collection look capped, as one above the 1,000 cap would; the count route is real.
	// The page loads by slug first, then by id.
	const collectionRoute = new RegExp(`/api/v1/collection/(${smart.slug}|${smart.id})$`);
	await page.route(collectionRoute, async (route) => {
		const response = await route.fetch();
		const body = (await response.json()) as Record<string, unknown>;
		await route.fulfill({
			response,
			json: { ...body, item_count: 1000, item_count_capped: true }
		});
	});
	const countRoute = /\/api\/v1\/collection\/[^/]+\/count$/;

	// Hold the count until the capped label has been seen, then the exact figure replaces it.
	let release!: () => void;
	const held = new Promise<void>((resolve) => (release = resolve));
	await page.route(countRoute, async (route) => {
		await held;
		await route.continue();
	});
	await page.goto(`/collections/${smart.slug}`);
	await expect(page.getByText('1,000+ items', { exact: true })).toBeVisible();
	release();
	await expect(page.getByText('3 items', { exact: true })).toBeVisible();
	await expect(page.getByText('1,000+ items', { exact: true })).toHaveCount(0);
	await page.unroute(countRoute);

	// A failing count offers a retry that fills in the figure.
	await page.route(countRoute, (route) =>
		route.fulfill({
			status: 500,
			contentType: 'application/json',
			body: JSON.stringify({ detail: 'Forced failure' })
		})
	);
	await page.reload();
	await expect(
		page.getByRole('alert').filter({ hasText: "Couldn't count the items" })
	).toBeVisible();
	await expect(page.getByText('1,000+ items', { exact: true })).toBeVisible();
	await page.unroute(countRoute);
	await page.getByRole('button', { name: 'Count exactly' }).click();
	await expect(page.getByText('3 items', { exact: true })).toBeVisible();
});

// Seeding 1,003 items through the API takes about 95 s (and clearing them as long again), too
// slow for every run, so this real-size check only runs with E2E_BULK=1. The default run covers
// the same page behaviour with a forged "capped" count above.
test('counts a really large smart collection exactly (E2E_BULK=1)', async ({ page, request }) => {
	test.skip(!process.env.E2E_BULK, 'Seeds 1,003 items; set E2E_BULK=1 to run it.');
	test.setTimeout(400_000);

	const tool = await makeItemType(request, uniqueName('Bulk'));
	const total = 1003;
	const created: string[] = [];
	for (let start = 0; start < total; start += 50) {
		const batch = await Promise.all(
			Array.from({ length: Math.min(50, total - start) }, async (_, i) => {
				const res = await request.post('/api/v1/node', {
					data: { name: `Bulk ${start + i}`, type: tool.slug }
				});
				expect(res.status(), await res.text()).toBe(201);
				return ((await res.json()) as { id: string }).id;
			})
		);
		created.push(...batch);
	}
	// Items are deleted concurrently below; a sequential delete of 1,003 items is slow.
	let smart: Smart | undefined;
	try {
		smart = await makeSmart(request, uniqueName('Bulk set'), {
			v: 1,
			where: { op: 'and', children: [{ kind: 'type', in: [tool.slug] }] },
			sort: []
		});

		// Hold the count until the capped label has been seen.
		let release!: () => void;
		const held = new Promise<void>((resolve) => (release = resolve));
		await page.route(/\/api\/v1\/collection\/[^/]+\/count$/, async (route) => {
			await held;
			await route.continue();
		});
		await page.goto(`/collections/${smart.slug}`);
		await expect(page.getByText('1,000+ items', { exact: true })).toBeVisible();
		release();
		await expect(page.getByText('1,003 items', { exact: true })).toBeVisible();
		await page.unroute(/\/api\/v1\/collection\/[^/]+\/count$/);

		// The list keeps the capped figure.
		await page.goto('/collections');
		await expect(page.getByRole('link', { name: new RegExp(smart.name) })).toContainText(
			'1,000+ items'
		);

		// A failing count offers a retry that fills in the figure.
		await page.route(/\/api\/v1\/collection\/[^/]+\/count$/, (route) =>
			route.fulfill({
				status: 500,
				contentType: 'application/json',
				body: JSON.stringify({ detail: 'Forced failure' })
			})
		);
		await page.goto(`/collections/${smart.slug}`);
		await expect(
			page.getByRole('alert').filter({ hasText: "Couldn't count the items" })
		).toBeVisible();
		await expect(page.getByText('1,000+ items', { exact: true })).toBeVisible();
		await page.unroute(/\/api\/v1\/collection\/[^/]+\/count$/);
		await page.getByRole('button', { name: 'Count exactly' }).click();
		await expect(page.getByText('1,003 items', { exact: true })).toBeVisible();
	} finally {
		if (smart) await request.delete(`/api/v1/collection/${smart.id}`);
		for (let i = 0; i < created.length; i += 50) {
			await Promise.all(created.slice(i, i + 50).map((id) => request.delete(`/api/v1/node/${id}`)));
		}
	}
});

// New collection: the kind choice (a list you fill, or a smart collection).
const newCollectionDialog = (page: Page) => page.getByRole('dialog', { name: 'New collection' });
const createButton = (page: Page) =>
	newCollectionDialog(page).getByRole('button', { name: 'Create collection' });

async function openNewCollection(page: Page) {
	await page.goto('/collections');
	await expect(page.getByRole('heading', { name: 'Collections', level: 1 })).toBeVisible();
	await page.getByRole('button', { name: 'New collection' }).first().click();
	await expect(newCollectionDialog(page)).toBeVisible();
}

/** Writes a screenshot of the open dialog when SHOTS_DIR is set (manual review only). */
async function shot(page: Page, file: string) {
	const dir = process.env.SHOTS_DIR;
	if (dir) await page.waitForTimeout(400);
	if (dir) await page.screenshot({ path: `${dir}/${file}.png` });
}

test.describe('New collection: kind choice', () => {
	test('creates a smart collection from a condition and opens it with its items', async ({
		page,
		request
	}) => {
		const tool = await makeTool(request);
		const names = await seedItems(request, tool);
		const name = uniqueName('Cheap parts');
		await openNewCollection(page);
		const dialog = newCollectionDialog(page);

		await expect(dialog.getByRole('radio', { name: 'List you fill', exact: true })).toBeChecked();
		await expect(dialog.getByRole('combobox', { name: 'Condition 1, field' })).toHaveCount(0);
		await shot(page, `manual-${test.info().project.name}`);

		await dialog.getByRole('radio', { name: 'Smart: matches conditions', exact: true }).check();
		await expect(dialog.getByRole('combobox', { name: 'Condition 1, field' })).toBeVisible();
		await dialog.getByLabel('Name').fill(name);
		await dialog.getByLabel('Description').fill('Heavy enough');

		// No condition yet: refused, with the reason shown.
		await expect(createButton(page)).toBeDisabled();
		await expect(dialog.getByText('Add at least one condition.')).toBeVisible();
		await shot(page, `smart-empty-${test.info().project.name}`);

		await fillRow(page, dialog, 1, {
			field: `${tool.label} › Weight`,
			operator: 'is at least',
			value: '5'
		});
		await expect(createButton(page)).toBeEnabled();
		await expect(dialog.getByText('Add at least one condition.')).toHaveCount(0);
		await shot(page, `smart-filled-${test.info().project.name}`);
		await page.emulateMedia({ colorScheme: 'dark' });
		await shot(page, `smart-filled-dark-${test.info().project.name}`);
		await page.emulateMedia({ colorScheme: 'light' });
		await createButton(page).click();

		await page.waitForURL(/\/collections\/(?!$)[^/]+$/);
		trackCollectionFromUrl(page);
		await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
		await expect(page.getByText('Smart', { exact: true })).toBeVisible();
		await expect(page.getByText('Heavy enough')).toBeVisible();
		await expect(itemLink(page, names.b)).toBeVisible();
		await expect(itemLink(page, names.c)).toBeVisible();
		await expect(itemLink(page, names.a)).toHaveCount(0);
	});

	test('refuses a smart collection with no condition, and a missing name first', async ({
		page
	}) => {
		await openNewCollection(page);
		const dialog = newCollectionDialog(page);
		await dialog.getByRole('radio', { name: 'Smart: matches conditions' }).check();
		await expect(createButton(page)).toBeDisabled();
		await expect(dialog.getByText('Give the collection a name.')).toBeVisible();
		await dialog.getByLabel('Name').fill(uniqueName('Nothing'));
		await expect(dialog.getByText('Add at least one condition.')).toBeVisible();
		await expect(createButton(page)).toBeDisabled();

		// Cancel discards the choice and the name.
		await dialog.getByRole('button', { name: 'Cancel' }).click();
		await expect(dialog).toHaveCount(0);
		await page.getByRole('button', { name: 'New collection' }).first().click();
		await expect(dialog.getByRole('radio', { name: 'List you fill' })).toBeChecked();
		await expect(dialog.getByLabel('Name')).toHaveValue('');
	});

	test('the list you fill still works as before', async ({ page }) => {
		const name = uniqueName('Manual');
		await openNewCollection(page);
		const dialog = newCollectionDialog(page);
		await dialog.getByLabel('Name').fill(name);
		await createButton(page).click();
		await page.waitForURL(/\/collections\/(?!$)[^/]+$/);
		trackCollectionFromUrl(page);
		await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
		await expect(page.getByText('Smart', { exact: true })).toHaveCount(0);
	});

	test('works from the keyboard alone', async ({ page }) => {
		await openNewCollection(page);
		const dialog = newCollectionDialog(page);
		// The dialog opens on its Close button; the next stop is the name.
		await expect(dialog.getByRole('button', { name: 'Close' })).toBeFocused();
		await page.keyboard.press('Tab');
		await expect(dialog.getByLabel('Name')).toBeFocused();
		await page.keyboard.type(uniqueName('Keys'));
		await page.keyboard.press('Tab');
		await expect(dialog.getByLabel('Description')).toBeFocused();
		await page.keyboard.press('Tab');
		await expect(dialog.getByRole('radio', { name: 'List you fill' })).toBeFocused();
		await page.keyboard.press('ArrowDown');
		await expect(dialog.getByRole('radio', { name: 'Smart: matches conditions' })).toBeChecked();
		// The match toggle comes first, then the first condition.
		const field = dialog.getByRole('combobox', { name: 'Condition 1, field' });
		for (let i = 0; i < 4 && !(await field.evaluate((el) => el === document.activeElement)); i++) {
			await page.keyboard.press('Tab');
		}
		await expect(field).toBeFocused();
		await page.keyboard.press('Escape');
		await expect(dialog).toHaveCount(0);
		await expect(page.getByRole('button', { name: 'New collection' }).first()).toBeFocused();
	});

	test('fits a phone: no horizontal overflow, and the sheet scrolls inside', async ({ page }) => {
		await page.setViewportSize({ width: 390, height: 844 });
		await openNewCollection(page);
		const dialog = newCollectionDialog(page);
		await shot(page, 'manual-phone');
		await dialog.getByRole('radio', { name: 'Smart: matches conditions' }).check();
		await expect(dialog.getByRole('combobox', { name: 'Condition 1, field' })).toBeVisible();
		await dialog.getByRole('button', { name: 'Add condition' }).first().click();
		const overflow = await page.evaluate(() => {
			const d = document.querySelector('[role="dialog"]') as HTMLElement;
			return {
				page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
				dialog: d.scrollWidth - d.clientWidth
			};
		});
		expect(overflow).toEqual({ page: 0, dialog: 0 });
		await expect(createButton(page)).toBeVisible();
		await shot(page, 'smart-phone');
		await page.emulateMedia({ colorScheme: 'dark' });
		await shot(page, 'smart-phone-dark');
	});
});
