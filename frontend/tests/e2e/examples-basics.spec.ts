import { test, expect } from './fixtures';
import { createItem, createItemType, uniqueName } from './helpers';
import { MUSIC, exampleData, install, openItem, remove } from './examples-helpers';

/**
 * Example packs: install, the Home line, the Examples filter and the first-run link. Installs are global per pack and the database is shared, so the spec is serial and every test cleans up through the API afterwards.
 */
test.describe.configure({ mode: 'serial' });

const { ownNames, cleanUp } = exampleData();

test.beforeEach(({ request }) => cleanUp(request));
test.afterEach(({ request }) => cleanUp(request));

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
