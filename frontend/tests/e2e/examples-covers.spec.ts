import { test, expect } from './fixtures';
import {
	type ApiNode,
	MOVIES,
	coverOf,
	exampleData,
	install,
	installViaApi,
	mediaOf,
	nodeNamed,
	nodesNamed,
	remove,
	removeViaApi,
	setOwnCover
} from './examples-helpers';

/**
 * Generated covers on example items. Serial, and every test cleans up through the API afterwards.
 */
test.describe.configure({ mode: 'serial' });

const { cleanUp } = exampleData();

test.beforeEach(({ request }) => cleanUp(request));
test.afterEach(({ request }) => cleanUp(request));

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
