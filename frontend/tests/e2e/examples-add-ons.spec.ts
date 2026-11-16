import { test, expect } from './fixtures';
import {
	GAMES,
	GAMES_EXTRAS,
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

/** Shared example packs need serial tests because the database is shared. */
test.describe.configure({ mode: 'serial' });

const { cleanUp } = exampleData();

test.beforeEach(({ request }) => cleanUp(request));
test.afterEach(({ request }) => cleanUp(request));

test('an add-on needs its base pack, then adds games with covers, links and a collection', async ({
	page,
	request
}) => {
	await page.goto('/library/examples');
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

	await page.goto('/library/examples');
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
	const collections = (await (await request.get('/api/v1/collections?limit=100')).json()) as {
		name: string;
	}[];
	expect(collections.some((c) => c.name === 'Weeknight picks')).toBe(false);
});

test('a stale page shows the server message when a prerequisite is gone', async ({
	page,
	request
}) => {
	await installViaApiMany(request, ['games']);
	await page.goto('/library/examples');
	const extras = packCard(page, 'Extra board games');
	const add = extras.getByRole('button', { name: /^Add Extra board games/ });
	await expect(add).toBeEnabled();

	// Another tab removes the prerequisite while this page still shows Add as available.
	await removeViaApi(request, 'games');
	await expect.poll(async () => (await nodesNamed(request, 'Lantern Harbour')).length).toBe(0);

	// The preview asks the server, which says the prerequisite is gone and offers no Add.
	await add.click();
	const preview = page.getByRole('dialog', { name: /^Add Extra board games/ });
	await expect(preview.getByText("This can't go ahead")).toBeVisible();
	await expect(preview).toContainText(/board games/i);
	await expect(preview.getByRole('button', { name: 'Add', exact: true })).toHaveCount(0);
	await preview.getByRole('button', { name: 'Cancel' }).click();
	// The page now shows what the server said.
	await expect(extras.getByText('Add Board games first.')).toBeVisible();
	await expect(extras.getByRole('button', { name: /^Add Extra board games/ })).toBeDisabled();
	expect(await nodesNamed(request, 'Quillfeather Quarry')).toHaveLength(0);
});

test('storage locations nest: an item shows where it is, and a location what it holds', async ({
	page,
	request
}) => {
	await installViaApiMany(request, ['games', 'storage']);
	const orchard = await nodeNamed(request, 'Pocket Orchard');

	await page.goto(`/items/${orchard.id}`);
	const path = page.getByRole('navigation', { name: 'Where this item is' });
	await expect(path).toBeVisible();
	for (const holder of ['Living room', 'Tall bookcase', 'Top shelf', 'Tin box'])
		await expect(path.getByRole('link', { name: holder })).toBeVisible();

	await path.getByRole('link', { name: 'Top shelf' }).click();
	const inside = page.getByRole('list', { name: 'Inside this item' });
	for (const held of ['Lantern Harbour', 'Tea Clipper Race', 'Tin box'])
		await expect(inside.getByRole('link', { name: held })).toBeVisible();
});
