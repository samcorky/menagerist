import { test, expect, type APIRequestContext } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * Totals on a collection page: the automatic ones (money added up per currency, numbers
 * averaged), adding one, removing one and going back to automatic. The database is shared, so
 * each test creates its own type, items and collection and removes them afterwards.
 */
test.describe.configure({ mode: 'serial' });

const { makeCollection, makeItem, makeItemType, addToCollection, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const SCHEMA = {
	type: 'object',
	properties: {
		price: { title: 'Price', type: 'object', 'x-menagerist': { kind: 'money' } },
		score: { title: 'Score', type: 'number' }
	}
};

/** A collection of three priced items (two in pounds, one in dollars) of a type of its own. */
async function pricedCollection(request: APIRequestContext) {
	const type = await makeItemType(request, uniqueName('Gadget'));
	const patched = await request.patch(`/api/v1/node-types/${type.id}`, {
		data: { attributes_schema: SCHEMA }
	});
	expect(patched.ok(), await patched.text()).toBeTruthy();
	const collection = await makeCollection(request, uniqueName('Totals'));
	const ids: string[] = [];
	for (const [price, currency, score] of [
		[10, 'GBP', 4],
		[5.5, 'GBP', 2],
		[3, 'USD', 3]
	] as const) {
		const item = await makeItem(request, uniqueName('Thing'), type.slug);
		const res = await request.patch(`/api/v1/nodes/${item.id}`, {
			data: { attributes: { price: { value: price, currency }, score } }
		});
		expect(res.ok(), await res.text()).toBeTruthy();
		ids.push(item.id);
	}
	await addToCollection(request, collection.id, ids);
	return collection;
}

test('shows automatic totals, one value per currency', async ({ page, request }) => {
	const collection = await pricedCollection(request);

	await page.goto(`/collections/${collection.id}`);

	const totals = page.getByRole('region', { name: 'Totals' });
	await expect(totals.getByText('Total price', { exact: true })).toBeVisible();
	await expect(totals).toContainText('£15.50');
	await expect(totals).toContainText('US$3.00');
	await expect(totals.getByText('Average score', { exact: true })).toBeVisible();
	await expect(totals).toContainText('3');
	await page.screenshot({ path: test.info().outputPath('totals-automatic.png') });
	await page.setViewportSize({ width: 390, height: 800 });
	await expect(totals).toBeVisible();
	await page.screenshot({ path: test.info().outputPath('totals-mobile.png') });
});

test('adds a total, removes one, and goes back to automatic', async ({ page, request }) => {
	const collection = await pricedCollection(request);
	await page.goto(`/collections/${collection.id}`);
	const totals = page.getByRole('region', { name: 'Totals' });
	await expect(totals).toContainText('£15.50');

	await totals.getByRole('button', { name: 'Edit totals' }).click();
	await totals.getByRole('button', { name: 'Add a total' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add a total' });
	const field = dialog.getByLabel('Field');
	const score = await field.locator('option', { hasText: 'Score' }).getAttribute('value');
	await field.selectOption(score!);
	await dialog.getByLabel('Show the').selectOption('max');
	await dialog.getByRole('button', { name: 'Add total' }).click();
	await expect(page.getByText('Total added')).toBeVisible();
	await expect(totals.getByText('Highest', { exact: false }).first()).toBeVisible();
	await expect(totals).toContainText('4');
	await page.screenshot({ path: test.info().outputPath('totals-added.png') });

	await totals.getByRole('button', { name: /^Remove Total price/ }).click();
	await expect(totals.getByText('Total price', { exact: true })).toHaveCount(0);

	await totals.getByRole('button', { name: 'Use automatic totals' }).click();
	await expect(totals.getByText('Total price', { exact: true })).toBeVisible();
	await expect(totals.getByRole('button', { name: 'Use automatic totals' })).toHaveCount(0);
});

test('keeps an empty choice: removing every total shows none', async ({ page, request }) => {
	const collection = await pricedCollection(request);
	await page.goto(`/collections/${collection.id}`);
	const totals = page.getByRole('region', { name: 'Totals' });
	await totals.getByRole('button', { name: 'Edit totals' }).click();

	await totals.getByRole('button', { name: /^Remove Total price/ }).click();
	await totals.getByRole('button', { name: /^Remove Average score/ }).click();

	await expect(totals.getByText('Total price', { exact: true })).toHaveCount(0);
	await page.reload();
	await expect(
		page.getByRole('region', { name: 'Totals' }).getByText('Total price', { exact: true })
	).toHaveCount(0);
});
