import { test, expect } from './fixtures';
import {
	GAMES,
	GAMES_EXTRAS,
	MOVIES,
	SOUNDTRACKS,
	collectionCard,
	coverOf,
	exampleData,
	install,
	installViaApiMany,
	mediaOf,
	nodeNamed,
	nodesNamed,
	packCard,
	remove,
	removeViaApi
} from './examples-helpers';

/**
 * Add-on packs: they need other packs, which blocks Add until those are in and Remove while the add-on is installed. Serial, and every test cleans up through the API afterwards.
 */
test.describe.configure({ mode: 'serial' });

const { cleanUp } = exampleData();

test.beforeEach(({ request }) => cleanUp(request));
test.afterEach(({ request }) => cleanUp(request));

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
