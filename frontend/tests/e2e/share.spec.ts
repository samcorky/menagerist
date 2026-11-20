import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * Share on an item and on a collection: the device's share sheet where the browser has one,
 * otherwise the link is copied. Headless Chromium on Linux has no share sheet, so the copy path
 * is the default here and the native one is stood in for.
 */
const { makeItem, makeCollection, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

/** Stands in for the browser's share sheet and records what it was given. */
async function stubShareSheet(page: Page) {
	await page.addInitScript(() => {
		const shared: { title?: string; url?: string }[] = [];
		(window as unknown as { shared: typeof shared }).shared = shared;
		navigator.share = async (data) => {
			shared.push({ title: data?.title, url: data?.url });
		};
	});
}

const sharedLinks = (page: Page) =>
	page.evaluate(
		() => (window as unknown as { shared?: { title?: string; url?: string }[] }).shared ?? []
	);

test.describe('without a share sheet', () => {
	test.beforeEach(({ context }) => context.grantPermissions(['clipboard-read', 'clipboard-write']));

	test('Share on an item copies its address', async ({ page, request }) => {
		const item = await makeItem(request, uniqueName('Share item'));
		await page.goto(`/items/${item.id}`);
		await page.getByRole('button', { name: 'Share' }).click();

		await expect(page.getByText('Link copied')).toBeVisible();
		const copied = await page.evaluate(() => navigator.clipboard.readText());
		expect(copied).toBe(new URL(`/items/${item.id}`, page.url()).href);
	});

	test('Share on a collection copies its address', async ({ page, request }) => {
		const collection = await makeCollection(request, uniqueName('Share collection'));
		await page.goto(`/collections/${collection.id}`);
		await expect(page.getByRole('heading', { name: collection.name })).toBeVisible();
		await page.getByRole('button', { name: 'Share' }).click();

		await expect(page.getByText('Link copied')).toBeVisible();
		const copied = await page.evaluate(() => navigator.clipboard.readText());
		expect(copied).toBe(page.url());
	});
});

test.describe('with a share sheet', () => {
	test('Share on an item hands its name and address to it', async ({ page, request }) => {
		await stubShareSheet(page);
		const item = await makeItem(request, uniqueName('Sheet item'));
		await page.goto(`/items/${item.id}`);
		await page.getByRole('button', { name: 'Share' }).click();

		await expect
			.poll(() => sharedLinks(page))
			.toEqual([{ title: item.name, url: new URL(`/items/${item.id}`, page.url()).href }]);
		// The sheet is its own confirmation, so there is no toast on top of it.
		await expect(page.getByText('Link copied')).toHaveCount(0);
	});

	test('Share on a collection hands its name and address to it', async ({ page, request }) => {
		await stubShareSheet(page);
		const collection = await makeCollection(request, uniqueName('Sheet collection'));
		await page.goto(`/collections/${collection.id}`);
		await expect(page.getByRole('heading', { name: collection.name })).toBeVisible();
		await page.getByRole('button', { name: 'Share' }).click();

		await expect
			.poll(() => sharedLinks(page))
			.toEqual([{ title: collection.name, url: page.url() }]);
	});
});
