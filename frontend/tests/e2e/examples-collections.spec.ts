import { test, expect, type Page } from './fixtures';
import { uniqueName } from './helpers';
import {
	FAMILY_NIGHT_ITEMS,
	GAMES,
	GAME_COLLECTIONS,
	collectionCard,
	exampleData,
	install,
	remove
} from './examples-helpers';

/**
 * Example packs that ship collections: listing, removal, kept collections and adoption on reinstall. Serial, and every test cleans up through the API afterwards.
 */
test.describe.configure({ mode: 'serial' });

const { makeCollection, addToCollection, trackCollectionFromUrl, cleanUp } = exampleData();

test.beforeEach(({ request }) => cleanUp(request));
test.afterEach(({ request }) => cleanUp(request));

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
