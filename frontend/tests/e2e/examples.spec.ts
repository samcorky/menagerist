import { test, expect, type APIRequestContext, type Page } from './fixtures';
import { createItem, createItemType, ownedData, removeExamplePacks, uniqueName } from './helpers';

/**
 * Example packs: install and remove from Settings > Examples, with the Home line and
 * empty-state link. Installs are global per pack and the database is shared, so the suite is
 * serial and every test cleans up through the API afterwards.
 */
test.describe.configure({ mode: 'serial' });

const MUSIC = /^Music/;
const MOVIES = /^Movies/;
const GAMES = /^Board games/;
const GAMES_EXTRAS = /^Extra board games/;
const SOUNDTRACKS = /^Film soundtracks/;
const GAME_COLLECTIONS = [
	{ name: 'Wishlist', count: '2 items' },
	{ name: 'Games for two', count: '2 items' },
	{ name: 'Family game night', count: '4 items' },
	{ name: 'Still to try', count: '3 items' }
];
const FAMILY_NIGHT_ITEMS = [
	'Slow Parcel Panic',
	'Tea Clipper Race',
	'Ministry of Mild Mischief',
	'Lantern Harbour'
];

const {
	makeCollection,
	addToCollection,
	trackCollectionFromUrl,
	cleanUp: cleanUpOwned
} = ownedData();

// Names of items this spec created or renamed, deleted again in cleanup.
let ownNames: string[] = [];
const ownTypeLabels: string[] = [];

async function cleanUp(request: APIRequestContext) {
	await removeExamplePacks(request);
	// Collections made here, including a kept example collection that was edited.
	await cleanUpOwned(request);
	const nodes = await request.get('/api/v1/node?limit=500');
	for (const node of (await nodes.json()) as { id: string; name: string }[]) {
		if (ownNames.includes(node.name)) await request.delete(`/api/v1/node/${node.id}`);
	}
	ownNames = [];
}

test.beforeEach(({ request }) => cleanUp(request));
test.afterEach(({ request }) => cleanUp(request));

async function install(page: Page, pack: RegExp) {
	await page.goto('/settings/examples');
	await page.getByRole('button', { name: new RegExp(`^Add ${pack.source.slice(1)}`) }).click();
	await expect(page.getByText('Examples added')).toBeVisible();
	await expect(
		page.getByRole('button', { name: new RegExp(`^Remove ${pack.source.slice(1)}`) })
	).toBeVisible();
}

async function remove(page: Page, pack: RegExp) {
	await page.goto('/settings/examples');
	await page.getByRole('button', { name: new RegExp(`^Remove ${pack.source.slice(1)}`) }).click();
	await page
		.getByRole('dialog', { name: 'Remove these examples?' })
		.getByRole('button', { name: 'Remove', exact: true })
		.click();
}

async function openItem(page: Page, name: string) {
	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill(name);
	await page.getByRole('link', { name }).first().click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);
	await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
}

test('installs a pack, shows the Home line, and keeps it dismissed after reload', async ({
	page
}) => {
	await install(page, MUSIC);

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill('Night Drive');
	const card = page.getByRole('link', { name: 'Night Drive' }).first();
	await expect(card).toBeVisible();
	await expect(card.getByText('Example', { exact: true })).toBeVisible();

	await page.getByRole('button', { name: 'Grid view' }).click();
	await expect(card).toBeVisible();
	await expect(card.getByText('Example', { exact: true })).toBeVisible();
	await page.getByRole('button', { name: 'List view' }).click();

	// Hiding examples removes them from the list and the choice survives a reload.
	const filter = page.getByLabel('Examples', { exact: true });
	await expect(filter).toHaveValue('all');
	await filter.selectOption({ label: 'Hide examples' });
	await expect(filter).toHaveValue('hide');
	await expect(page.getByRole('link', { name: 'Night Drive' })).toHaveCount(0);

	await page.reload();
	await expect(filter).toHaveValue('hide');
	await page.getByPlaceholder('Search your items…').fill('Night Drive');
	await expect(page.getByText('Everything that matched is a hidden example.')).toBeVisible();
	await expect(page.getByRole('link', { name: 'Night Drive' })).toHaveCount(0);

	await page.getByRole('button', { name: 'Show all items' }).click();
	await expect(filter).toHaveValue('all');
	await expect(page.getByRole('link', { name: 'Night Drive' }).first()).toBeVisible();

	await page.goto('/');
	const line = page.getByText('You have example items.');
	await expect(line).toBeVisible();
	await page.getByRole('button', { name: 'Dismiss' }).click();
	await expect(line).toHaveCount(0);

	await page.reload();
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	await expect(line).toHaveCount(0);
});

test('filters to only examples, keeps the choice, and restores everything', async ({ page }) => {
	await install(page, MUSIC);
	const own = uniqueName('Night Own');
	ownNames.push(own);
	await createItem(page, { name: own });

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill('Night');
	const filter = page.getByLabel('Examples', { exact: true });
	const example = page.getByRole('link', { name: 'Night Drive' }).first();
	const mine = page.getByRole('link', { name: own }).first();
	await expect(example).toBeVisible();
	await expect(mine).toBeVisible();

	await filter.selectOption({ label: 'Only examples' });
	await expect(filter).toHaveValue('only');
	await expect(example).toBeVisible();
	await expect(page.getByRole('link', { name: own })).toHaveCount(0);

	await page.reload();
	await expect(filter).toHaveValue('only');
	await page.getByPlaceholder('Search your items…').fill('Night');
	await expect(example).toBeVisible();
	await expect(page.getByRole('link', { name: own })).toHaveCount(0);

	await filter.selectOption({ label: 'All items' });
	await expect(filter).toHaveValue('all');
	await expect(example).toBeVisible();
	await expect(mine).toBeVisible();

	// A search matching only the user's item leaves nothing under "Only examples".
	await filter.selectOption({ label: 'Only examples' });
	await page.getByPlaceholder('Search your items…').fill(own);
	await expect(page.getByText('No example items match.')).toBeVisible();
	await page.getByRole('button', { name: 'Show all items' }).click();
	await expect(filter).toHaveValue('all');
	await expect(mine).toBeVisible();
});

test('a stale Only examples filter keeps the select so you can go back to All', async ({
	page
}) => {
	await install(page, MUSIC);
	const own = uniqueName('Stale Own');
	ownNames.push(own);
	await createItem(page, { name: own });

	await page.goto('/items');
	const filter = page.getByLabel('Examples', { exact: true });
	await filter.selectOption({ label: 'Only examples' });
	await expect(filter).toHaveValue('only');

	await remove(page, MUSIC);
	await expect(page.getByRole('button', { name: /^Add Music/ })).toBeVisible();

	await page.goto('/items');
	await expect(filter).toHaveValue('only');
	await expect(page.getByText('No example items match.')).toBeVisible();
	await filter.selectOption({ label: 'All items' });
	await expect(page.getByRole('link', { name: own }).first()).toBeVisible();

	// Back on All with no examples left, the select goes away.
	await page.reload();
	await expect(filter).toHaveCount(0);
});

test('follows a connection between example items', async ({ page }) => {
	await install(page, MUSIC);
	await openItem(page, 'Night Drive');
	// The item's own header card, so no other badge on the page can match.
	await expect(
		page.locator('[data-slot="card"]').first().getByText('Example', { exact: true })
	).toBeVisible();

	await page.getByRole('link', { name: 'The Velvet Static', exact: true }).first().click();
	await expect(page.getByText('The Velvet Static', { exact: true }).first()).toBeVisible();
	await expect(page.getByRole('link', { name: 'Night Drive' }).first()).toBeVisible();
});

test('removing a pack removes its items and item types', async ({ page }) => {
	await install(page, MUSIC);
	const ownType = uniqueName('Plain Type');
	ownTypeLabels.push(ownType);
	await createItemType(page, { label: ownType });

	await page.goto('/settings/item-types');
	const typeCard = (text: string) =>
		page.locator('[data-slot="card"]').filter({ has: page.getByText(text, { exact: true }) });
	const exampleCard = typeCard('music-record');
	await expect(exampleCard).toBeVisible();
	await expect(exampleCard.getByText('Example', { exact: true })).toBeVisible();
	await expect(typeCard(ownType)).toBeVisible();
	await expect(typeCard(ownType).getByText('Example', { exact: true })).toHaveCount(0);

	await remove(page, MUSIC);
	await expect(page.getByText(/^Removed /)).toBeVisible();
	await expect(page.getByRole('button', { name: /^Add Music/ })).toBeVisible();

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill('Night Drive');
	await expect(page.getByRole('link', { name: 'Night Drive' })).toHaveCount(0);
	await expect(page.getByLabel('Examples', { exact: true })).toHaveCount(0);
	await expect(page.getByText('Example', { exact: true })).toHaveCount(0);

	await page.goto('/settings/item-types');
	await expect(page.getByRole('heading', { name: 'Item types' })).toBeVisible();
	await expect(page.getByText('music-record', { exact: true })).toHaveCount(0);
	await expect(page.getByText(/^music-/)).toHaveCount(0);
	await expect(typeCard(ownType)).toBeVisible();
	await expect(page.getByText('Example', { exact: true })).toHaveCount(0);
});

test('keeps an edited example item on removal and says why', async ({ page }) => {
	await install(page, MUSIC);
	await openItem(page, 'Paper Lanterns');

	const edited = uniqueName('Edited Lanterns');
	ownNames.push(edited);
	await page.getByRole('button', { name: 'Edit', exact: true }).click();
	await page.getByLabel('Name').fill(edited);
	await page.getByRole('button', { name: 'Save changes' }).click();
	await expect(page.getByText(edited, { exact: true }).first()).toBeVisible();

	await remove(page, MUSIC);
	await expect(page.getByRole('region', { name: /Notifications/ })).toContainText(
		'kept because you edited them'
	);
	await expect(page.getByText('item was kept because you edited them.')).toBeVisible();

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill(edited);
	const keptCard = page.getByRole('link', { name: edited }).first();
	await expect(keptCard).toBeVisible();
	await expect(keptCard.getByText('Example', { exact: true })).toHaveCount(0);
	await expect(page.getByLabel('Examples', { exact: true })).toHaveCount(0);

	await keptCard.click();
	await expect(page.getByText(edited, { exact: true }).first()).toBeVisible();
	await expect(page.getByText('Example', { exact: true })).toHaveCount(0);
});

test('keeps an example item that has your own connection', async ({ page }) => {
	await install(page, MOVIES);
	const own = uniqueName('My own item');
	ownNames.push(own);
	await createItem(page, { name: own });

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill('');
	const firstExample = await page.request
		.get('/api/v1/node?limit=500')
		.then((r) => r.json() as Promise<{ id: string; name: string; type: string | null }[]>)
		.then((nodes) => nodes.find((n) => n.type?.startsWith('movies-')));
	expect(firstExample).toBeTruthy();
	ownNames.push(firstExample!.name);

	await page.goto(`/items/${firstExample!.id}`);
	await expect(page.getByText(firstExample!.name, { exact: true }).first()).toBeVisible();
	// Example items already have connections, so scope the label to the form's own input.
	await page.getByRole('textbox', { name: 'Connection', exact: true }).fill('related-to');
	const targetSearch = page.getByPlaceholder('Search items…');
	await targetSearch.fill(own);
	await page
		.getByRole('button', { name: new RegExp(own) })
		.first()
		.click();
	await targetSearch.blur();
	await page.waitForTimeout(250);
	await page.getByRole('button', { name: /^Connect items?$/ }).click();
	await expect(page.getByRole('link', { name: own })).toBeVisible();

	await remove(page, MOVIES);
	await expect(
		page.getByText('item was kept because they have your connections, files or collections.')
	).toBeVisible();

	await page.goto(`/items/${firstExample!.id}`);
	await expect(page.getByText(firstExample!.name, { exact: true }).first()).toBeVisible();
});

test('reinstalls a pack after removing it', async ({ page }) => {
	await install(page, MUSIC);
	await remove(page, MUSIC);
	await expect(page.getByRole('button', { name: /^Add Music/ })).toBeVisible();

	await install(page, MUSIC);
	await openItem(page, 'Night Drive');
});

test('a clashing item type slug gives a friendly error and creates nothing', async ({
	page,
	request
}) => {
	await createItemType(page, { label: 'Music Person' });

	await page.goto('/settings/examples');
	await page.getByRole('button', { name: /^Add Music/ }).click();
	await expect(page.getByText("Couldn't add these examples")).toBeVisible();
	await expect(page.getByRole('button', { name: /^Add Music/ })).toBeVisible();

	const nodes = (await (await request.get('/api/v1/node?limit=500')).json()) as { name: string }[];
	expect(nodes.some((n) => n.name === 'Night Drive')).toBe(false);
	const types = (await (await request.get('/api/v1/node-type?limit=500')).json()) as {
		slug: string;
	}[];
	expect(types.some((t) => t.slug === 'music-record')).toBe(false);
});

test('the empty-state link opens the examples page, and only shows with no items', async ({
	page,
	request
}) => {
	const link = page.getByRole('link', { name: 'Or look around with some examples' });

	const probe = await request.get('/api/v1/node?limit=1');
	if (Number(probe.headers()['total-count'] ?? '0') === 0) {
		await page.goto('/');
		await link.click();
		await expect(page).toHaveURL(/\/settings\/examples$/);
		await expect(page.getByRole('heading', { name: 'Examples' })).toBeVisible();
	}

	await install(page, MUSIC);
	await page.goto('/');
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	await expect(link).toHaveCount(0);
});

// Example packs that ship collections.

const collectionCard = (page: Page, name: string) =>
	page.getByRole('link').filter({ hasText: new RegExp(`^\\s*${name}(\\s|$)`) });

/** Installs the games pack, renames 'Family game night' and removes the pack (it is kept). */
async function installEditAndRemoveGames(page: Page, renamed: string) {
	await install(page, GAMES);
	await page.goto('/collections');
	await collectionCard(page, 'Family game night').click();
	await page.waitForURL(/\/collections\/(?!$)[^/]+$/);
	trackCollectionFromUrl(page);
	await page.getByRole('button', { name: 'Edit', exact: true }).click();
	const dialog = page.getByRole('dialog', { name: 'Edit collection' });
	await dialog.getByLabel('Name').fill(renamed);
	await dialog.getByRole('button', { name: 'Save' }).click();
	await expect(page.getByRole('heading', { name: renamed, level: 1 })).toBeVisible();
	await remove(page, GAMES);
	await expect(page.getByRole('region', { name: /Notifications/ })).toContainText('Removed');
}

test('a pack with collections lists them with an Example badge and item counts', async ({
	page,
	request
}) => {
	const own = uniqueName('My own collection');
	await makeCollection(request, own);
	await install(page, GAMES);

	const card = page
		.locator('[data-slot="card"]')
		.filter({ has: page.getByText('Board games', { exact: true }) });
	await expect(card).toContainText('4 collections');

	await page.goto('/collections');
	for (const { name, count } of GAME_COLLECTIONS) {
		const link = collectionCard(page, name);
		await expect(link).toBeVisible();
		await expect(link.getByText('Example', { exact: true })).toBeVisible();
		await expect(link).toContainText(count);
	}
	const mine = collectionCard(page, own);
	await expect(mine).toBeVisible();
	await expect(mine.getByText('Example', { exact: true })).toHaveCount(0);

	await collectionCard(page, 'Family game night').click();
	const heading = page.getByRole('heading', { name: 'Family game night', level: 1 });
	await expect(heading).toBeVisible();
	await expect(heading.locator('xpath=..').getByText('Example', { exact: true })).toBeVisible();
	for (const item of FAMILY_NIGHT_ITEMS) {
		await expect(page.getByRole('link', { name: item }).first()).toBeVisible();
	}
});

test('removing a pack removes its collections and items', async ({ page, request }) => {
	await install(page, GAMES);
	await remove(page, GAMES);
	await expect(page.getByRole('region', { name: /Notifications/ })).toContainText(
		/Removed .*4 collections/
	);
	await expect(page.getByRole('button', { name: /^Add Board games/ })).toBeVisible();

	await page.goto('/collections');
	await expect(page.getByRole('heading', { name: 'Collections', level: 1 })).toBeVisible();
	for (const { name } of GAME_COLLECTIONS) {
		await expect(collectionCard(page, name)).toHaveCount(0);
	}
	const nodes = (await (await request.get('/api/v1/node?limit=500')).json()) as {
		type: string | null;
	}[];
	expect(nodes.some((n) => n.type?.startsWith('games-'))).toBe(false);
});

test('an edited example collection is kept with its items and stops being an example', async ({
	page
}) => {
	const renamed = uniqueName('Edited night');
	await installEditAndRemoveGames(page, renamed);
	const toasts = page.getByRole('region', { name: /Notifications/ });
	await expect(toasts).toContainText('kept because you edited them');
	await expect(toasts).toContainText(
		'kept because they have your connections, files or collections'
	);

	await page.goto('/collections');
	const kept = collectionCard(page, renamed);
	await expect(kept).toBeVisible();
	await expect(kept.getByText('Example', { exact: true })).toHaveCount(0);
	await expect(kept).toContainText('4 items');
	for (const name of ['Wishlist', 'Games for two', 'Still to try']) {
		await expect(collectionCard(page, name)).toHaveCount(0);
	}

	await kept.click();
	await expect(page.getByRole('heading', { name: renamed, level: 1 })).toBeVisible();
	await expect(page.getByText('Example', { exact: true })).toHaveCount(0);
	for (const item of FAMILY_NIGHT_ITEMS) {
		await expect(page.getByRole('link', { name: item }).first()).toBeVisible();
	}
});

test('an example item on your own collection is kept when the pack goes', async ({
	page,
	request
}) => {
	const own = await makeCollection(request, uniqueName('My games'));
	await install(page, GAMES);
	const nodes = (await (await request.get('/api/v1/node?limit=500')).json()) as {
		id: string;
		name: string;
	}[];
	const orchard = nodes.find((n) => n.name === 'Pocket Orchard');
	expect(orchard).toBeTruthy();
	await addToCollection(request, own.id, [orchard!.id]);

	await remove(page, GAMES);
	await expect(page.getByRole('region', { name: /Notifications/ })).toContainText('kept because');

	await page.goto('/collections');
	await expect(collectionCard(page, own.name)).toContainText('1 item');
	for (const { name } of GAME_COLLECTIONS) {
		await expect(collectionCard(page, name)).toHaveCount(0);
	}
	await page.goto(`/items/${orchard!.id}`);
	await expect(page.getByText('Pocket Orchard', { exact: true }).first()).toBeVisible();
});

test('reinstalling after keeping items adopts them instead of duplicating', async ({
	page,
	request
}) => {
	const renamed = uniqueName('Edited night');
	await installEditAndRemoveGames(page, renamed);
	const list = async () =>
		(await (await request.get('/api/v1/node?limit=500')).json()) as { name: string }[];
	expect((await list()).filter((n) => n.name === 'Lantern Harbour')).toHaveLength(1);

	await page.goto('/settings/examples');
	await page.getByRole('button', { name: /^Add Board games/ }).click();
	await expect(page.getByText('Examples added')).toBeVisible();
	await expect(page.getByText(/you'd kept (was|were) already here/)).toBeVisible();

	for (const item of FAMILY_NIGHT_ITEMS) {
		expect((await list()).filter((n) => n.name === item)).toHaveLength(1);
	}
	await page.goto('/collections');
	await expect(collectionCard(page, renamed)).toHaveCount(1);
});

// Generated covers on example items.

// A valid 1x1 PNG standing in for a cover the person uploads.
const OWN_COVER = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
	'base64'
);

type ApiNode = { id: string; name: string; type: string | null };
type ApiMedia = { id: string; filename: string; attribute_key: string | null };

async function nodesNamed(request: APIRequestContext, name: string): Promise<ApiNode[]> {
	const nodes = (await (await request.get('/api/v1/node?limit=500')).json()) as ApiNode[];
	return nodes.filter((n) => n.name === name);
}

async function nodeNamed(request: APIRequestContext, name: string): Promise<ApiNode> {
	const found = await nodesNamed(request, name);
	expect(found).toHaveLength(1);
	return found[0];
}

async function mediaOf(request: APIRequestContext, nodeId: string): Promise<ApiMedia[]> {
	const res = await request.get(`/api/v1/media/for-node/${nodeId}`);
	return res.ok() ? ((await res.json()) as ApiMedia[]) : [];
}

const coverOf = async (request: APIRequestContext, nodeId: string) =>
	(await mediaOf(request, nodeId)).find((m) => m.attribute_key === 'cover');

/** Uploads an image and makes it the node's cover, replacing any current one (as the UI does). */
async function setOwnCover(request: APIRequestContext, nodeId: string) {
	const res = await request.post('/api/v1/media/attached', {
		multipart: {
			file: { name: 'mine.png', mimeType: 'image/png', buffer: OWN_COVER },
			target_type: 'node',
			target_id: nodeId
		}
	});
	expect(res.ok(), await res.text()).toBeTruthy();
	const asset = (await res.json()) as { media_id?: string; asset_id?: string; id?: string };
	const assetId = asset.media_id ?? asset.asset_id ?? asset.id;
	const cover = await request.post(`/api/v1/media/${assetId}/attachments/cover`, {
		data: { target_type: 'node', target_id: nodeId }
	});
	expect(cover.ok(), await cover.text()).toBeTruthy();
}

async function installViaApi(request: APIRequestContext, pack: string) {
	const res = await request.put(`/api/v1/example/${pack}/installation`);
	expect(res.ok()).toBeTruthy();
}

async function removeViaApi(request: APIRequestContext, pack: string) {
	const res = await request.delete(`/api/v1/example/${pack}/installation`);
	expect(res.ok()).toBeTruthy();
}

test('a film example shows a loaded cover and a person example shows none', async ({
	page,
	request
}) => {
	await install(page, MOVIES);
	const film = await nodeNamed(request, 'Cold Harbour');
	const nodes = (await (await request.get('/api/v1/node?limit=500')).json()) as ApiNode[];
	const person = nodes.find((n) => n.type === 'movies-person')!;

	await page.goto(`/items/${film.id}`);
	const image = page.locator('img[src*="/media/"]').first();
	await expect(image).toBeVisible();
	await expect
		.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth))
		.toBeGreaterThan(0);

	await page.goto(`/items/${person.id}`);
	await expect(page.getByText(person.name, { exact: true }).first()).toBeVisible();
	await expect(page.locator('img[src*="/media/"]')).toHaveCount(0);
	expect(await mediaOf(request, person.id)).toHaveLength(0);
});

test('removing a pack removes its items and their covers', async ({ page, request }) => {
	await install(page, MOVIES);
	const film = await nodeNamed(request, 'Cold Harbour');
	const cover = await coverOf(request, film.id);
	expect(cover).toBeTruthy();

	await remove(page, MOVIES);
	await expect(page.getByRole('region', { name: /Notifications/ })).toContainText('Removed');

	expect(await nodesNamed(request, 'Cold Harbour')).toHaveLength(0);
	expect(await mediaOf(request, film.id)).toHaveLength(0);
	expect((await request.get(`/api/v1/media/${cover!.id}`)).status()).toBe(404);
});

test('a replaced cover keeps its game through removal and reinstall', async ({ request }) => {
	await installViaApi(request, 'games');
	const game = await nodeNamed(request, 'Lantern Harbour');
	expect(await coverOf(request, game.id)).toBeTruthy();

	await setOwnCover(request, game.id);
	expect((await coverOf(request, game.id))?.filename).toBe('mine.png');

	await removeViaApi(request, 'games');
	expect(await nodesNamed(request, 'Tea Clipper Race')).toHaveLength(0);
	const kept = await nodeNamed(request, 'Lantern Harbour');
	expect(kept.id).toBe(game.id);
	expect((await coverOf(request, kept.id))?.filename).toBe('mine.png');

	await installViaApi(request, 'games');
	expect(await nodesNamed(request, 'Lantern Harbour')).toHaveLength(1);
	expect((await nodeNamed(request, 'Lantern Harbour')).id).toBe(game.id);
	expect((await coverOf(request, game.id))?.filename).toBe('mine.png');
	expect(await nodesNamed(request, 'Tea Clipper Race')).toHaveLength(1);
});

test('your own cover on an example game survives removal and reinstall', async ({ request }) => {
	await installViaApi(request, 'games');
	const game = await nodeNamed(request, 'Pocket Orchard');
	const packCover = await coverOf(request, game.id);
	expect(packCover).toBeTruthy();

	// Take the pack's cover off first, so the game's only cover is the person's own.
	const detach = await request.delete(`/api/v1/media/${packCover!.id}/attachments`, {
		data: { target_type: 'node', target_id: game.id, attribute_key: 'cover' }
	});
	expect(detach.ok(), await detach.text()).toBeTruthy();
	expect(await coverOf(request, game.id)).toBeUndefined();
	await setOwnCover(request, game.id);

	await removeViaApi(request, 'games');
	expect((await nodeNamed(request, 'Pocket Orchard')).id).toBe(game.id);
	expect((await coverOf(request, game.id))?.filename).toBe('mine.png');

	await installViaApi(request, 'games');
	expect(await nodesNamed(request, 'Pocket Orchard')).toHaveLength(1);
	expect((await coverOf(request, game.id))?.filename).toBe('mine.png');
});

// Add-on packs: they need other packs, which blocks Add until those are in and Remove while
// the add-on is installed.

const packCard = (page: Page, title: string) =>
	page.locator('[data-slot="card"]').filter({ has: page.getByText(title, { exact: true }) });

async function installViaApiMany(request: APIRequestContext, packs: string[]) {
	for (const pack of packs) {
		const res = await request.put(`/api/v1/example/${pack}/installation`);
		expect(res.ok(), await res.text()).toBeTruthy();
	}
}

test('an add-on needs its base pack, then adds games with covers, links and a collection', async ({
	page,
	request
}) => {
	await page.goto('/settings/examples');
	const extras = packCard(page, 'Extra board games');
	await expect(extras).toContainText('Needs Board games');
	const add = extras.getByRole('button', { name: /^Add Extra board games/ });
	await expect(add).toBeDisabled();
	await expect(extras.getByText('Add Board games first.')).toBeVisible();
	await expect(add).toHaveAttribute('aria-describedby', 'blocked-games-extras');

	await install(page, GAMES);
	await page.reload();
	await expect(extras.getByRole('button', { name: /^Add Extra board games/ })).toBeEnabled();
	await expect(extras.getByText('Add Board games first.')).toHaveCount(0);
	await install(page, GAMES_EXTRAS);

	const game = await nodeNamed(request, 'Quillfeather Quarry');
	await page.goto(`/items/${game.id}`);
	const image = page.locator('img[src*="/media/"]').first();
	await expect(image).toBeVisible();
	await expect
		.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth))
		.toBeGreaterThan(0);
	await expect(page.getByRole('link', { name: 'Marrow Lane Press' }).first()).toBeVisible();

	await page.goto('/collections');
	await collectionCard(page, 'Weeknight picks').click();
	for (const name of [
		'Marzipan Moors',
		'Tidewrack Tavern',
		'Pocket Orchard',
		'Slow Parcel Panic'
	]) {
		await expect(page.getByRole('link', { name }).first()).toBeVisible();
	}
});

test('a base pack cannot be removed while its add-on is installed, then both go', async ({
	page,
	request
}) => {
	await installViaApiMany(request, ['games', 'games-extras']);
	const extra = await nodeNamed(request, 'Quillfeather Quarry');
	expect(await coverOf(request, extra.id)).toBeTruthy();

	await page.goto('/settings/examples');
	const base = packCard(page, 'Board games');
	await expect(base.getByRole('button', { name: /^Remove Board games/ })).toBeDisabled();
	await expect(base.getByText('Remove Extra board games first.')).toBeVisible();

	await remove(page, GAMES_EXTRAS);
	await expect(page.getByRole('button', { name: /^Add Extra board games/ })).toBeVisible();
	await expect(base.getByRole('button', { name: /^Remove Board games/ })).toBeEnabled();
	await remove(page, GAMES);
	await expect(page.getByRole('button', { name: /^Add Board games/ })).toBeVisible();

	expect(await nodesNamed(request, 'Quillfeather Quarry')).toHaveLength(0);
	expect(await nodesNamed(request, 'Lantern Harbour')).toHaveLength(0);
	expect(await mediaOf(request, extra.id)).toHaveLength(0);
	const collections = (await (await request.get('/api/v1/collection?limit=100')).json()) as {
		name: string;
	}[];
	expect(collections.some((c) => c.name === 'Weeknight picks')).toBe(false);
});

test('a bridge add-on needs both packs and shows its connection, then blocks both', async ({
	page,
	request
}) => {
	await installViaApiMany(request, ['music']);
	await page.goto('/settings/examples');
	const bridge = packCard(page, 'Film soundtracks');
	await expect(bridge).toContainText('Needs Music');
	await expect(bridge.getByRole('button', { name: /^Add Film soundtracks/ })).toBeDisabled();
	await expect(bridge.getByText('Add Movies first.')).toBeVisible();

	await install(page, MOVIES);
	await page.reload();
	await expect(bridge.getByRole('button', { name: /^Add Film soundtracks/ })).toBeEnabled();
	await install(page, SOUNDTRACKS);

	const film = await nodeNamed(request, 'Cold Harbour');
	await page.goto(`/items/${film.id}`);
	// The film sees the connection from its side, with the reverse label.
	await expect(page.getByText('Soundtrack', { exact: true }).first()).toBeVisible();
	await page.getByRole('link', { name: 'Night Drive' }).first().click();
	await expect(page.getByText('Soundtrack of', { exact: true }).first()).toBeVisible();
	await expect(page.getByRole('link', { name: 'Cold Harbour' }).first()).toBeVisible();

	await page.goto('/settings/examples');
	for (const base of ['Music', 'Movies']) {
		const card = packCard(page, base === 'Music' ? 'Music: records, gigs and friends' : 'Movies');
		await expect(card.getByRole('button', { name: new RegExp(`^Remove ${base}`) })).toBeDisabled();
		await expect(card.getByText('Remove Film soundtracks first.')).toBeVisible();
	}
});

test('a stale page shows the server message when a prerequisite is gone', async ({
	page,
	request
}) => {
	await installViaApiMany(request, ['games']);
	await page.goto('/settings/examples');
	const extras = packCard(page, 'Extra board games');
	const add = extras.getByRole('button', { name: /^Add Extra board games/ });
	await expect(add).toBeEnabled();

	// Another tab removes the prerequisite while this page still shows Add as available.
	await removeViaApi(request, 'games');
	await expect.poll(async () => (await nodesNamed(request, 'Lantern Harbour')).length).toBe(0);

	await add.click();
	await expect(page.getByText("Couldn't add these examples")).toBeVisible();
	await expect(page.getByRole('region', { name: /Notifications/ })).toContainText(/board games/i);
	await expect(extras.getByText('Add Board games first.')).toBeVisible();
	await expect(extras.getByRole('button', { name: /^Add Extra board games/ })).toBeDisabled();
	expect(await nodesNamed(request, 'Quillfeather Quarry')).toHaveLength(0);
});
