import { test, expect } from './fixtures';
import {
	MOVIES,
	MUSIC,
	exampleData,
	install,
	nodeNamed,
	packCard,
	remove
} from './examples-helpers';

/**
 * Links between packs: Music's soundtrack connections to Movies appear once both are added, in
 * either order, and never block removal. Serial, and every test cleans up through the API.
 */
test.describe.configure({ mode: 'serial' });

const { cleanUp } = exampleData();

test.beforeEach(({ request }) => cleanUp(request));
test.afterEach(({ request }) => cleanUp(request));

test('music and movies connect themselves and removal is never blocked', async ({
	page,
	request
}) => {
	await page.goto('/settings/examples');
	await expect(packCard(page, 'Music: records, gigs and friends')).toContainText(
		'Also connects to Movies when both are added'
	);

	await install(page, MUSIC);
	await install(page, MOVIES);

	const film = await nodeNamed(request, 'Cold Harbour');
	await page.goto(`/items/${film.id}`);
	await expect(page.getByText('Soundtrack', { exact: true }).first()).toBeVisible();
	await page.getByRole('link', { name: 'Night Drive' }).first().click();
	await expect(page.getByText('Soundtrack of', { exact: true }).first()).toBeVisible();

	await page.goto('/settings/examples');
	await remove(page, MOVIES);
	const record = await nodeNamed(request, 'Night Drive');
	await page.goto(`/items/${record.id}`);
	await expect(page.getByText('Soundtrack of', { exact: true })).toHaveCount(0);

	await page.goto('/settings/examples');
	await install(page, MOVIES);
	await page.goto(`/items/${record.id}`);
	await expect(page.getByText('Soundtrack of', { exact: true }).first()).toBeVisible();
});

test('adding movies first gives the same connections', async ({ page, request }) => {
	await install(page, MOVIES);
	await install(page, MUSIC);

	const record = await nodeNamed(request, 'Thirteen Bells');
	await page.goto(`/items/${record.id}`);
	await expect(page.getByText('Soundtrack of', { exact: true }).first()).toBeVisible();
	await expect(page.getByRole('link', { name: 'Marmalade' }).first()).toBeVisible();
});
