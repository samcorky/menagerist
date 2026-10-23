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
import { OWN_COVER } from './examples-helpers';

/**
 * The description, name, media and "in collection" conditions: the builder rows, saving, stale
 * references, linked copies, cycles and isolation. The database is shared, so every test makes
 * its own item type and unique names and removes what it made.
 */
test.describe.configure({ mode: 'serial' });

const { makeCollection, makeItemType, trackCollection, trackCollectionFromUrl, cleanUp } =
	ownedData();

const seededItemIds: string[] = [];

test.afterEach(async ({ request }) => {
	for (const id of seededItemIds.splice(0)) await request.delete(`/api/v1/node/${id}`);
	await cleanUp(request);
});

type Smart = { id: string; slug: string; name: string };

/** A word that is unique to the call, so searches only ever find this test's items. */
const word = (prefix: string) => uniqueName(prefix).replace(/\W+/g, '');

async function makeItem(
	request: APIRequestContext,
	name: string,
	extra: { description?: string; type?: string } = {}
) {
	const res = await request.post('/api/v1/node', { data: { name, ...extra } });
	expect(res.status(), await res.text()).toBe(201);
	const created = (await res.json()) as { id: string };
	seededItemIds.push(created.id);
	return created;
}

async function attachImage(request: APIRequestContext, itemId: string) {
	const res = await request.post('/api/v1/media/attached', {
		multipart: {
			file: { name: 'mine.png', mimeType: 'image/png', buffer: OWN_COVER },
			target_type: 'node',
			target_id: itemId
		}
	});
	expect(res.ok(), await res.text()).toBeTruthy();
}

async function addToCollection(request: APIRequestContext, collectionId: string, itemId: string) {
	const res = await request.put(`/api/v1/collection/${collectionId}/item`, {
		data: { item_ids: [itemId] }
	});
	expect(res.ok(), await res.text()).toBeTruthy();
}

async function makeSmart(
	request: APIRequestContext,
	name: string,
	children: unknown[]
): Promise<Smart> {
	const res = await request.post('/api/v1/collection', {
		data: { name, definition: { v: 1, where: { op: 'and', children }, sort: [] } }
	});
	expect(res.status(), await res.text()).toBe(201);
	const created = (await res.json()) as Smart;
	trackCollection(created.id);
	return created;
}

const itemLink = (page: Page, name: string) => page.getByRole('link', { name: new RegExp(name) });
const filtersDialog = (page: Page) => page.getByRole('dialog', { name: 'Filters' });
const conditionsDialog = (page: Page) => page.getByRole('dialog', { name: 'Edit conditions' });
const narrowedBar = (page: Page) => page.getByRole('region', { name: 'Narrowed view' });

/** Picks one of the general subjects (such as "Media") for a row. */
async function pickSubject(page: Page, dialog: Locator, n: number, label: string) {
	await dialog.getByRole('combobox', { name: `Condition ${n}, field` }).click();
	await page.getByPlaceholder('Search fields…').fill(label);
	await page.getByRole('option', { name: label, exact: true }).first().click();
	await expect(page.getByRole('listbox')).toHaveCount(0);
}

const operator = (dialog: Locator, n: number) => dialog.getByLabel(`Condition ${n}, operator`);
const value = (dialog: Locator, n: number) => dialog.getByLabel(`Condition ${n}, value`);

/** Adds a collection to a collection row's picker. */
async function pickCollection(page: Page, dialog: Locator, n: number, name: string) {
	await dialog.getByRole('combobox', { name: `Condition ${n}, value, add a collection` }).click();
	await page.getByPlaceholder('Search collections…').fill(name);
	await page.getByRole('option', { name, exact: true }).click();
	await expect(page.getByRole('listbox')).toHaveCount(0);
	await expect(
		dialog.getByRole('button', { name: `Remove ${name} from Condition ${n}` })
	).toBeVisible();
}

async function openItemsFilters(page: Page) {
	await page.getByRole('button', { name: /^Filters/ }).click();
	const dialog = filtersDialog(page);
	await expect(dialog).toBeVisible();
	return dialog;
}

async function done(page: Page, dialog: Locator) {
	await dialog.getByRole('button', { name: 'Done' }).click();
	await expect(dialog).toHaveCount(0);
}

// The first visit of each route is slower; keep it out of the real tests' timing.
test('warms up the routes', async ({ page, request }) => {
	test.setTimeout(120_000);
	const smart = await makeSmart(request, uniqueName('Warm'), [{ kind: 'favourite', value: true }]);
	for (const path of ['/collections', `/collections/${smart.slug}`, '/items']) {
		await page.goto(path, { waitUntil: 'networkidle' });
	}
});

test('builds searches with description, name, media and collection rows and saves one', async ({
	page,
	request
}) => {
	const s = word('Cond');
	const alpha = `Alpha${s}`;
	const bravo = `Bravo${s}`;
	const charlie = `Charlie${s}`;
	const a = await makeItem(request, alpha, { description: 'A signed copy of the first' });
	const b = await makeItem(request, bravo);
	await makeItem(request, charlie, { description: 'Plain' });
	await attachImage(request, a.id);
	const manual = await makeCollection(request, uniqueName('Shelf'));
	await addToCollection(request, manual.id, a.id);
	const smart = await makeSmart(request, uniqueName('Bravo only'), [
		{ kind: 'name', op: '~', value: bravo }
	]);
	expect(b.id).toBeTruthy();

	await page.goto('/items');
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	let dialog = await openItemsFilters(page);

	// Row 1: the name contains the unique word, so only this test's items are left.
	await pickSubject(page, dialog, 1, 'Name');
	await value(dialog, 1).fill(s);
	await dialog.getByRole('button', { name: 'Add condition' }).first().click();

	// Row 2: no description.
	await pickSubject(page, dialog, 2, 'Description');
	await operator(dialog, 2).selectOption({ label: 'is empty' });
	await done(page, dialog);
	await expect(itemLink(page, bravo)).toBeVisible();
	await expect(itemLink(page, alpha)).toHaveCount(0);
	await expect(itemLink(page, charlie)).toHaveCount(0);

	// The description contains a word (case-insensitive).
	dialog = await openItemsFilters(page);
	await operator(dialog, 2).selectOption({ label: 'contains' });
	await value(dialog, 2).fill('SIGNED');
	await done(page, dialog);
	await expect(itemLink(page, alpha)).toBeVisible();
	await expect(itemLink(page, bravo)).toHaveCount(0);

	// Media: has an image, then has no media.
	dialog = await openItemsFilters(page);
	await pickSubject(page, dialog, 2, 'Media');
	await value(dialog, 2).selectOption({ label: 'an image' });
	await done(page, dialog);
	await expect(itemLink(page, alpha)).toBeVisible();
	await expect(itemLink(page, bravo)).toHaveCount(0);

	dialog = await openItemsFilters(page);
	await operator(dialog, 2).selectOption({ label: 'has no' });
	await done(page, dialog);
	await expect(itemLink(page, bravo)).toBeVisible();
	await expect(itemLink(page, charlie)).toBeVisible();
	await expect(itemLink(page, alpha)).toHaveCount(0);

	// In a manual collection, then in none of it.
	dialog = await openItemsFilters(page);
	await pickSubject(page, dialog, 2, 'In collection');
	await pickCollection(page, dialog, 2, manual.name);
	await done(page, dialog);
	await expect(itemLink(page, alpha)).toBeVisible();
	await expect(itemLink(page, bravo)).toHaveCount(0);

	dialog = await openItemsFilters(page);
	await operator(dialog, 2).selectOption({ label: 'is in none of' });
	await done(page, dialog);
	await expect(itemLink(page, bravo)).toBeVisible();
	await expect(itemLink(page, charlie)).toBeVisible();
	await expect(itemLink(page, alpha)).toHaveCount(0);

	// In a smart collection.
	dialog = await openItemsFilters(page);
	await dialog.getByRole('button', { name: `Remove ${manual.name} from Condition 2` }).click();
	await operator(dialog, 2).selectOption({ label: 'is in any of' });
	await pickCollection(page, dialog, 2, smart.name);
	await done(page, dialog);
	await expect(itemLink(page, bravo)).toBeVisible();
	await expect(itemLink(page, charlie)).toHaveCount(0);

	// Save the search as a smart collection: its count and the plain-words summary.
	const name = uniqueName('Saved conditions');
	await page.getByRole('button', { name: 'Save as smart collection' }).click();
	const save = page.getByRole('dialog', { name: 'Save as smart collection' });
	await save.getByLabel('Name').fill(name);
	await save.getByRole('button', { name: 'Save smart collection' }).click();
	await page.waitForURL(/\/collections\/(?!$)[^/]+$/);
	trackCollectionFromUrl(page);

	await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
	await expect(page.getByText('1 item', { exact: true })).toBeVisible();
	await expect(itemLink(page, bravo)).toBeVisible();
	const conditions = page.getByRole('list', { name: 'Conditions' });
	await expect(conditions).toContainText(`Name contains “${s}”`);
	await expect(conditions).toContainText(`In ${smart.name}`);

	await page.goto('/collections');
	await expect(page.getByRole('link', { name: new RegExp(name) })).toContainText('1 item');
});

test('a deleted collection used by a condition shows as deleted, with a warning', async ({
	page,
	request
}) => {
	const manual = await makeCollection(request, uniqueName('Doomed'));
	const smart = await makeSmart(request, uniqueName('Uses doomed'), [
		{ kind: 'collection', mode: 'any', in: [manual.id] }
	]);
	const gone = await request.delete(`/api/v1/collection/${manual.id}`);
	expect(gone.ok(), await gone.text()).toBeTruthy();

	await page.goto(`/collections/${smart.slug}`);
	await expect(page.getByRole('heading', { name: smart.name, level: 1 })).toBeVisible();
	const conditions = page.getByRole('list', { name: 'Conditions' });
	await expect(conditions).toContainText('a collection that no longer exists');
	await expect(conditions.getByLabel('Warning')).toBeVisible();
	await expect(page.getByText('No items match these conditions')).toBeVisible();

	await page.getByRole('button', { name: 'Edit conditions' }).first().click();
	const dialog = conditionsDialog(page);
	await expect(dialog.getByText('Deleted collection', { exact: true })).toBeVisible();
	await expect(
		dialog.getByText('A collection here no longer exists, so it matches nothing.')
	).toBeVisible();
});

test('Save as new, linked from a manual collection follows its parent', async ({
	page,
	request
}) => {
	const s = word('Man');
	const first = await makeItem(request, `First${s}`);
	const parent = await makeCollection(request, uniqueName('Parent shelf'));
	await addToCollection(request, parent.id, first.id);
	const outsider = await makeItem(request, `Outsider${s}`);
	expect(outsider.id).toBeTruthy();

	await page.goto(`/collections/${parent.id}`);
	await page.getByPlaceholder('Search this collection…').fill(s);
	const bar = narrowedBar(page);
	await expect(bar).toBeVisible();
	await expect(bar.getByRole('button', { name: 'Save as new smart collection' })).toHaveCount(0);
	await bar.getByRole('button', { name: 'Save as new, linked to this collection' }).click();
	const save = page.getByRole('dialog', { name: 'Save as new, linked to this collection' });
	const name = uniqueName('Child of shelf');
	await save.getByLabel('Name').fill(name);
	await save.getByRole('button', { name: 'Save smart collection' }).click();
	await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
	trackCollectionFromUrl(page);

	await expect(itemLink(page, `First${s}`)).toBeVisible();
	await expect(itemLink(page, `Outsider${s}`)).toHaveCount(0);
	await expect(page.getByRole('list', { name: 'Conditions' })).toContainText(parent.name);

	// A new member of the parent shows up in the child after a reload.
	const second = await makeItem(request, `Second${s}`);
	await addToCollection(request, parent.id, second.id);
	await page.reload();
	await expect(itemLink(page, `Second${s}`)).toBeVisible();
	await expect(itemLink(page, `First${s}`)).toBeVisible();
});

test('Save as new, linked from a smart collection follows its parent', async ({
	page,
	request
}) => {
	const s = word('Smt');
	const tool = await makeItemType(request, uniqueName('Kit'));
	await makeItem(request, `One${s}`, { type: tool.slug });
	const parent = await makeSmart(request, uniqueName('Parent kit'), [
		{ kind: 'type', in: [tool.slug] }
	]);

	await page.goto(`/collections/${parent.slug}`);
	await page.getByPlaceholder('Search this collection…').fill(s);
	const bar = narrowedBar(page);
	await bar.getByRole('button', { name: 'Save as new, linked to this collection' }).click();
	const save = page.getByRole('dialog', { name: 'Save as new, linked to this collection' });
	const name = uniqueName('Child of kit');
	await save.getByLabel('Name').fill(name);
	await save.getByRole('button', { name: 'Save smart collection' }).click();
	await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
	trackCollectionFromUrl(page);
	await expect(itemLink(page, `One${s}`)).toBeVisible();

	await makeItem(request, `Two${s}`, { type: tool.slug });
	await page.reload();
	await expect(itemLink(page, `Two${s}`)).toBeVisible();
	await expect(itemLink(page, `One${s}`)).toBeVisible();
});

test('a collection cannot refer to itself: the save is refused with a message', async ({
	page,
	request
}) => {
	const s = word('Cyc');
	const first = await makeSmart(request, uniqueName('Cycle one'), [
		{ kind: 'name', op: '~', value: s }
	]);
	const second = await makeSmart(request, uniqueName('Cycle two'), [
		{ kind: 'collection', mode: 'any', in: [first.id] }
	]);

	// The API refuses the direct reference and the loop through the second collection.
	for (const target of [first.id, second.id]) {
		const res = await request.patch(`/api/v1/collection/${first.id}`, {
			data: {
				definition: {
					v: 1,
					where: { op: 'and', children: [{ kind: 'collection', mode: 'any', in: [target] }] },
					sort: []
				}
			}
		});
		expect(res.status(), await res.text()).toBe(400);
	}

	// The page shows the message and keeps the dialog open. The picker leaves the collection
	// itself out, so the loop goes through the second one.
	await page.goto(`/collections/${first.slug}`);
	await page.getByRole('button', { name: 'Edit conditions' }).first().click();
	const dialog = conditionsDialog(page);
	await dialog.getByRole('button', { name: 'Add condition' }).first().click();
	await pickSubject(page, dialog, 2, 'In collection');
	await expect(
		dialog.getByRole('combobox', { name: 'Condition 2, value, add a collection' })
	).toBeVisible();
	await pickCollection(page, dialog, 2, second.name);
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(dialog.getByRole('alert')).toContainText('cannot refer to itself');
	await expect(dialog).toBeVisible();
});

test('another user cannot see or count your collections through a condition', async ({
	request,
	browser,
	workerBaseURL,
	workerSession
}) => {
	const s = word('Iso');
	const mine = await makeItem(request, `Mine${s}`);
	const shelf = await makeCollection(request, uniqueName('Private shelf'));
	await addToCollection(request, shelf.id, mine.id);
	const smart = await makeSmart(request, uniqueName('Private smart'), [
		{ kind: 'name', op: '~', value: s }
	]);

	const admin = await playwrightRequest.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const other = await createUserViaApi(admin, workerBaseURL, { prefix: 'cond-b' });
	await admin.dispose();
	const b = await asUser(browser, other);
	try {
		const theirs = await b.request.post('/api/v1/node', { data: { name: `Theirs${s}` } });
		expect(theirs.status()).toBe(201);
		const theirId = ((await theirs.json()) as { id: string }).id;

		const search = async (mode: 'any' | 'none', ids: string[]) => {
			const res = await b.request.post('/api/v1/node/search', {
				data: {
					query: {
						v: 1,
						where: {
							op: 'and',
							children: [
								{ kind: 'name', op: '~', value: s },
								{ kind: 'collection', mode, in: ids }
							]
						},
						sort: []
					}
				}
			});
			expect(res.status(), await res.text()).toBe(200);
			return (await res.json()) as {
				items: { id: string }[];
				total: number;
				warnings: { message: string }[];
			};
		};

		// Your collections are stale for them: nothing matches, in either direction, with a
		// warning, and your items never show up.
		for (const ids of [[shelf.id], [smart.id], [shelf.id, smart.id]]) {
			for (const mode of ['any', 'none'] as const) {
				const result = await search(mode, ids);
				expect(result.items).toEqual([]);
				expect(result.total).toBe(0);
				expect(result.warnings.length).toBeGreaterThan(0);
			}
		}
		// Their own item is still found without the condition, so the zero above is the condition.
		const plain = await b.request.get(`/api/v1/node?q=Theirs${s}`);
		expect(((await plain.json()) as { id: string }[]).map((n) => n.id)).toContain(theirId);

		// A smart collection of theirs cannot be made to count yours either.
		const made = await b.request.post('/api/v1/collection', {
			data: {
				name: `Spy ${s}`,
				definition: {
					v: 1,
					where: { op: 'and', children: [{ kind: 'collection', mode: 'any', in: [shelf.id] }] },
					sort: []
				}
			}
		});
		expect(made.status(), await made.text()).toBe(201);
		const spy = (await made.json()) as { id: string; item_count: number };
		expect(spy.item_count).toBe(0);
		expect(
			(
				(await (await b.request.get(`/api/v1/collection/${spy.id}/count`)).json()) as {
					count: number;
				}
			).count
		).toBe(0);
		await b.request.delete(`/api/v1/collection/${spy.id}`);
		await b.request.delete(`/api/v1/node/${theirId}`);
	} finally {
		await b.context.close();
	}
});

test('the collections picker shows an error with Retry when the list cannot be loaded', async ({
	page
}) => {
	let failing = true;
	await page.route(/\/api\/v1\/collection(\?[^/]*)?$/, (route) => {
		if (failing && route.request().method() === 'GET') {
			return route.fulfill({
				status: 500,
				contentType: 'application/json',
				body: JSON.stringify({ detail: 'Forced failure' })
			});
		}
		return route.continue();
	});

	await page.goto('/items');
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	const dialog = await openItemsFilters(page);
	await pickSubject(page, dialog, 1, 'In collection');
	await expect(
		dialog.getByRole('alert').filter({ hasText: 'Could not load your collections.' })
	).toBeVisible();

	failing = false;
	await dialog.getByRole('button', { name: 'Condition 1, retry loading collections' }).click();
	await expect(
		dialog.getByRole('combobox', { name: 'Condition 1, value, add a collection' })
	).toBeVisible();
	await expect(dialog.getByText('Could not load your collections.')).toHaveCount(0);
});
