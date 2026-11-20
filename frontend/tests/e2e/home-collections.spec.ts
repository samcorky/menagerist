import { test, expect, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** Any collection, manual or smart, can be shown on Home with its count and newest items. */
const { makeCollection, makeItem, addToCollection, trackCollection, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const homeSection = (page: Page, name: string) =>
	page
		.locator('main [data-slot="collapsible"]')
		.filter({ has: page.getByRole('heading', { name, exact: true }) });

test('shows a manual collection on Home from its page, then takes it off from Home', async ({
	page,
	request
}) => {
	const collection = await makeCollection(request, uniqueName('Wishlist'));
	const item = await makeItem(request, uniqueName('Tardis'));
	await addToCollection(request, collection.id, [item.id]);

	await page.goto(`/collections/${collection.id}`);
	const toggle = page.getByRole('button', { name: 'Show on Home' });
	await expect(toggle).toHaveAttribute('aria-pressed', 'false');
	await toggle.click();
	await expect(toggle).toHaveAttribute('aria-pressed', 'true');
	await expect(page.getByText('Shown on Home')).toBeVisible();

	await page.goto('/');
	const section = homeSection(page, collection.name);
	await expect(section).toBeVisible();
	await expect(section.getByRole('link', { name: /View all 1/ })).toBeVisible();
	await expect(section.getByRole('link', { name: new RegExp(item.name) })).toBeVisible();

	await section.getByRole('button', { name: `Remove ${collection.name} from Home` }).click();
	await expect(homeSection(page, collection.name)).toHaveCount(0);
	await page.reload();
	await expect(page.getByRole('heading', { name: 'Newly added' })).toBeVisible();
	await expect(homeSection(page, collection.name)).toHaveCount(0);

	await page.goto(`/collections/${collection.id}`);
	await expect(page.getByRole('button', { name: 'Show on Home' })).toHaveAttribute(
		'aria-pressed',
		'false'
	);
});

test('shows a smart collection on Home with the items its conditions match', async ({
	page,
	request
}) => {
	const item = await makeItem(request, uniqueName('Dalek'));
	const res = await request.post('/api/v1/collections', {
		data: {
			name: uniqueName('Exterminate'),
			definition: {
				v: 1,
				where: { op: 'and', children: [{ kind: 'name', op: '=', value: item.name }] },
				sort: []
			}
		}
	});
	expect(res.status()).toBe(201);
	const smart = (await res.json()) as { id: string; name: string };
	trackCollection(smart.id);

	await page.goto(`/collections/${smart.id}`);
	await page.getByRole('button', { name: 'Show on Home' }).click();
	await expect(page.getByText('Shown on Home')).toBeVisible();

	await page.goto('/');
	const section = homeSection(page, smart.name);
	await expect(section.getByRole('link', { name: /View all 1/ })).toBeVisible();
	await expect(section.getByRole('link', { name: new RegExp(item.name) })).toBeVisible();
});
