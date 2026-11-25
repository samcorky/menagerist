import { test, expect } from './fixtures';
import { collectionCard, exampleData, install, remove } from './examples-helpers';

// The packs that show parent types (#772).
const FORMATS = /^Record formats/;
const FILM = /^Film formats/;
const CURRENCY = /^Currency/;

const { cleanUp } = exampleData();

test.beforeEach(({ request }) => cleanUp(request));
test.afterEach(({ request }) => cleanUp(request));

test('a pack with a parent type lists the parent with its subtypes, and removing it leaves none', async ({
	page
}) => {
	await install(page, FORMATS);

	await page.goto('/library/item-types');
	const parent = page.getByRole('listitem').filter({ hasText: 'Music media' }).first();
	await expect(parent).toContainText('4 subtypes');
	for (const name of ['Vinyl', 'CD', 'Cassette', 'MiniDisc']) {
		await expect(page.getByRole('listitem').filter({ hasText: name }).first()).toBeVisible();
	}

	await remove(page, FORMATS);
	await page.goto('/library/item-types');
	await expect(page.getByText('Music media')).toHaveCount(0);
	await expect(page.getByText('Vinyl')).toHaveCount(0);
});

test('the pack’s collection finds every format, and a subtype shows its parent', async ({
	page
}) => {
	await install(page, FORMATS);

	await page.goto('/collections');
	await expect(collectionCard(page, 'All music media')).toContainText('7 items');

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill('Kind of Blue');
	await page.getByRole('link', { name: 'Kind of Blue' }).first().click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);
	// A subtype is shown with its parent, and takes the parent's fields.
	await expect(page.getByText('Music media').first()).toBeVisible();
	await expect(page.getByText('Vinyl').first()).toBeVisible();
	await expect(page.getByText('Catalogue number').first()).toBeVisible();
	await expect(page.getByText('Matrix / runout').first()).toBeVisible();
});

test('the film and currency packs install and remove cleanly too', async ({ page }) => {
	await install(page, FILM);
	await install(page, CURRENCY);

	await page.goto('/library/item-types');
	await expect(page.getByRole('listitem').filter({ hasText: 'Film media' }).first()).toContainText(
		'4 subtypes'
	);
	await expect(page.getByRole('listitem').filter({ hasText: 'Currency' }).first()).toContainText(
		'3 subtypes'
	);

	await remove(page, FILM);
	await remove(page, CURRENCY);
	await page.goto('/library/item-types');
	await expect(page.getByText('Film media')).toHaveCount(0);
	await expect(page.getByText('Banknote')).toHaveCount(0);
});
