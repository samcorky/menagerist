import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * The trail and the Contains list on the item page, for a box in a shed that holds a bag.
 */
const { makeItem, cleanUp } = ownedData();
const edgeTypeIds: string[] = [];

test.afterEach(async ({ request }) => {
	for (const id of edgeTypeIds.splice(0)) await request.delete(`/api/v1/edge-types/${id}`);
	await cleanUp(request);
});

test('shows where an item sits and what it holds', async ({ page, request }) => {
	const suffix = uniqueName('x').replace(/\W+/g, '');
	const label = `Contains ${suffix}`;
	const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
	const res = await request.post('/api/v1/edge-types', {
		data: { slug, label, reverse_label: `Inside ${suffix}`, directional: true }
	});
	expect(res.status(), await res.text()).toBe(201);
	edgeTypeIds.push(((await res.json()) as { id: string }).id);
	const shed = await makeItem(request, `Shed${suffix}`);
	const box = await makeItem(request, `Box${suffix}`);
	const bag = await makeItem(request, `Bag${suffix}`);
	for (const [outer, inner] of [
		[shed, box],
		[box, bag]
	]) {
		const edge = await request.post('/api/v1/edges', {
			data: { source_id: outer.id, target_id: inner.id, type: slug }
		});
		expect(edge.status(), await edge.text()).toBe(201);
	}

	// The bag is in the box, which is in the shed: the trail runs outermost first.
	await page.goto(`/items/${bag.id}`);
	const trail = page.getByRole('navigation', { name: 'Where this item is' });
	await expect(trail.getByText(`Inside ${suffix}`)).toBeVisible();
	await expect(trail.getByRole('link')).toHaveText([shed.name, box.name]);
	await trail.getByRole('link', { name: box.name }).click();

	// The box holds the bag; the shed's list also reaches the bag through the box.
	await expect(page).toHaveURL(new RegExp(box.id));
	const inBox = page.getByRole('list', { name: 'Inside this item' });
	await expect(inBox.getByRole('link')).toHaveText([bag.name]);

	await page.goto(`/items/${shed.id}`);
	const inShed = page.getByRole('list', { name: 'Inside this item' });
	await expect(inShed.getByRole('link')).toHaveText([box.name, bag.name]);
	await expect(inShed.getByText('2 levels in')).toBeVisible();
	await expect(page.getByRole('navigation', { name: 'Where this item is' })).toHaveCount(0);
});
