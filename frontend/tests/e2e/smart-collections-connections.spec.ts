import {
	test,
	expect,
	request as playwrightRequest,
	apiSessionOptions,
	type APIRequestContext,
	type Page
} from './fixtures';
import { asUser, createUserViaApi, ownedData, uniqueName } from './helpers';

/**
 * Connection conditions in the Filters panel on the Items page. Each test makes its own
 * relationship and items; only connections of that relationship are asked about.
 */
test.describe.configure({ mode: 'serial' });

const { makeItem, makeItemType, trackCollection, trackCollectionFromUrl, cleanUp } = ownedData();
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

type Created = { id: string; slug: string; name: string };

/**
 * Films with a "viewing of" relationship (a viewing is the source, the film the target). The
 * film type is the scope, so other tests' items never match. `watched` has a viewing; `unseen` has none.
 */
async function seedFilms(request: APIRequestContext) {
	const suffix = uniqueName('f').replace(/\W+/g, '');
	const filmType = await makeItemType(request, `Film ${suffix}`);
	const viewingType = await makeItemType(request, `Viewing ${suffix}`);
	const label = `Viewing of ${suffix}`;
	const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
	const res = await request.post('/api/v1/edge-type', {
		data: { slug, label, reverse_label: `Viewings ${suffix}`, directional: true }
	});
	expect(res.status(), await res.text()).toBe(201);
	const edgeType = (await res.json()) as { id: string };
	edgeTypeIds.push(edgeType.id);

	const watched = await makeItem(request, `Watched${suffix}`, filmType.slug);
	const unseen = await makeItem(request, `Unseen${suffix}`, filmType.slug);
	const viewing = await makeItem(request, `Evening${suffix}`, viewingType.slug);
	await connect(request, viewing.id, watched.id, slug);
	return { suffix, filmType, viewingType, label, slug, edgeType, watched, unseen, viewing };
}

async function connect(request: APIRequestContext, source: string, target: string, type: string) {
	const edge = await request.post('/api/v1/edge', {
		data: { source_id: source, target_id: target, type }
	});
	expect(edge.status(), await edge.text()).toBe(201);
}

/** The saved search "films that have no viewing of them". */
function noViewing(films: Awaited<ReturnType<typeof seedFilms>>) {
	return {
		v: 1,
		where: {
			op: 'and',
			children: [
				{ kind: 'type', in: [films.filmType.slug] },
				{ kind: 'connection', mode: 'none', relationship: films.slug, direction: 'in' }
			]
		},
		sort: []
	};
}

async function makeSmart(request: APIRequestContext, name: string, definition: unknown) {
	const res = await request.post('/api/v1/collection', { data: { name, definition } });
	expect(res.status(), await res.text()).toBe(201);
	const created = (await res.json()) as Created;
	trackCollection(created.id);
	return created;
}

test('builds "films with no viewing", saves it, and a new viewing takes the film out', async ({
	page,
	request
}) => {
	const films = await seedFilms(request);
	const name = uniqueName('Unseen films');
	await page.goto(`/items?type=${films.filmType.slug}`);
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	await page.getByRole('button', { name: /^Filters/ }).click();
	const dialog = await addConnectionRow(page);
	await dialog.getByLabel('Condition 1, operator').selectOption({ label: 'Has no connection' });
	await dialog
		.getByLabel('Condition 1, relationship')
		.selectOption({ label: `${films.label} / Viewings ${films.suffix}` });
	await dialog.getByLabel('Condition 1, direction').selectOption({ label: 'To this item' });
	await expect(link(page, films.unseen.name)).toBeVisible();
	await expect(link(page, films.watched.name)).toHaveCount(0);
	await dialog.getByRole('button', { name: 'Done' }).click();

	await page.getByRole('button', { name: 'Save as smart collection' }).click();
	const save = page.getByRole('dialog', { name: 'Save as smart collection' });
	await save.getByLabel('Name').fill(name);
	await save.getByRole('button', { name: 'Save smart collection' }).click();
	await page.waitForURL(/\/collections\/(?!$)[^/]+$/);
	trackCollectionFromUrl(page);

	await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
	await expect(link(page, films.unseen.name)).toBeVisible();
	await expect(link(page, films.watched.name)).toHaveCount(0);
	await expect(page.getByText('1 item', { exact: true })).toBeVisible();

	// A viewing of the unseen film takes it out on reload.
	const another = await makeItem(request, `Matinee${films.suffix}`, films.viewingType.slug);
	await connect(request, another.id, films.unseen.id, films.slug);
	await page.reload();
	await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
	await expect(link(page, films.unseen.name)).toHaveCount(0);
	await expect(page.getByText('No items match these conditions')).toBeVisible();
});

test('builds "connected to an item" and "a linked item of a type", and saves the second', async ({
	page,
	request
}) => {
	const films = await seedFilms(request);
	const name = uniqueName('Viewed films');
	await page.goto(`/items?type=${films.filmType.slug}`);
	await page.getByRole('button', { name: /^Filters/ }).click();
	const dialog = await addConnectionRow(page);
	await dialog
		.getByLabel('Condition 1, relationship')
		.selectOption({ label: `${films.label} / Viewings ${films.suffix}` });
	await dialog.getByLabel('Condition 1, direction').selectOption({ label: 'To this item' });

	// Connected to one named item.
	await dialog.getByLabel('Condition 1, operator').selectOption({ label: 'Is connected to' });
	await dialog.getByRole('combobox', { name: 'Condition 1, item' }).click();
	await page.getByPlaceholder('Search items…').fill(films.viewing.name);
	await page.getByRole('option', { name: new RegExp(films.viewing.name) }).click();
	await expect(link(page, films.watched.name)).toBeVisible();
	await expect(link(page, films.unseen.name)).toHaveCount(0);

	// A linked item that is a viewing; the film type has none, so a film type matches nothing.
	await dialog.getByLabel('Condition 1, operator').selectOption({ label: 'Has a connection' });
	await dialog.getByRole('button', { name: 'Condition 1, filter the linked item' }).click();
	await dialog.getByRole('combobox', { name: 'Condition 2, field' }).click();
	await page.getByPlaceholder('Search fields…').fill('Type');
	await page.getByRole('option', { name: 'Type', exact: true }).first().click();
	const types = dialog.getByRole('group', { name: 'Condition 2, value' });
	await types.getByRole('button', { name: films.filmType.label, exact: true }).click();
	await expect(link(page, films.watched.name)).toHaveCount(0);
	await types.getByRole('button', { name: films.filmType.label, exact: true }).click();
	await types.getByRole('button', { name: films.viewingType.label, exact: true }).click();
	await expect(link(page, films.watched.name)).toBeVisible();
	await expect(link(page, films.unseen.name)).toHaveCount(0);
	await dialog.getByRole('button', { name: 'Done' }).click();

	await page.getByRole('button', { name: 'Save as smart collection' }).click();
	const save = page.getByRole('dialog', { name: 'Save as smart collection' });
	await save.getByLabel('Name').fill(name);
	await save.getByRole('button', { name: 'Save smart collection' }).click();
	await page.waitForURL(/\/collections\/(?!$)[^/]+$/);
	trackCollectionFromUrl(page);
	await expect(link(page, films.watched.name)).toBeVisible();
	await expect(link(page, films.unseen.name)).toHaveCount(0);
});

test('a deleted relationship type shows a warning and an empty list, not an error', async ({
	page,
	request
}) => {
	const films = await seedFilms(request);
	const smart = await makeSmart(request, uniqueName('Stale link'), noViewing(films));
	await page.goto(`/collections/${smart.slug}`);
	await expect(link(page, films.unseen.name)).toBeVisible();

	await request.delete(`/api/v1/edge/${await edgeIdOf(request, films.watched.id)}`);
	const del = await request.delete(`/api/v1/edge-type/${films.edgeType.id}`);
	expect(del.ok(), await del.text()).toBeTruthy();

	await page.reload();
	await expect(page.getByRole('heading', { name: smart.name, level: 1 })).toBeVisible();
	await expect(page.getByText(/no longer exists/).first()).toBeVisible();
	await expect(page.getByText('No items match these conditions')).toBeVisible();
	await expect(link(page, films.unseen.name)).toHaveCount(0);

	await page.goto('/collections');
	const card = page.getByRole('link', { name: new RegExp(smart.name) });
	await expect(card).toBeVisible();
	await expect(card).toContainText('No items');
});

async function edgeIdOf(request: APIRequestContext, itemId: string): Promise<string> {
	const res = await request.get(`/api/v1/edge?node_id=${itemId}`);
	expect(res.ok(), await res.text()).toBeTruthy();
	const body = (await res.json()) as { id: string }[] | { items: { id: string }[] };
	return (Array.isArray(body) ? body : body.items)[0].id;
}

test('another user cannot open a smart collection that has a connection condition', async ({
	browser,
	request,
	workerBaseURL,
	workerSession
}) => {
	const films = await seedFilms(request);
	const smart = await makeSmart(request, uniqueName('Private link'), noViewing(films));

	const admin = await playwrightRequest.newContext(apiSessionOptions(workerBaseURL, workerSession));
	const other = await createUserViaApi(admin, workerBaseURL, { prefix: 'conn-b' });
	await admin.dispose();
	const b = await asUser(browser, other);

	await b.page.goto(`/collections/${smart.slug}`);
	await expect(b.page.getByRole('heading', { name: 'Collection not found' })).toBeVisible();
	await expect(b.page.getByText(films.unseen.name)).toHaveCount(0);
	expect((await b.request.get(`/api/v1/collection/${smart.id}`)).status()).toBe(404);
	expect((await b.request.get(`/api/v1/node?collection=${smart.id}`)).status()).toBe(404);
	await b.context.close();
});
