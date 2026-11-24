import { test, expect } from './fixtures';
import { openQuickCapture, ownedData, uniqueName } from './helpers';

/** Connect a new item to another while capturing it (#498). */
test.describe.configure({ mode: 'serial' });

const { makeItem, cleanUp } = ownedData();
const edgeTypeIds: string[] = [];

test.afterEach(async ({ request }) => {
	await cleanUp(request);
	for (const id of edgeTypeIds.splice(0)) await request.delete(`/api/v1/edge-types/${id}`);
});

async function makeEdgeType(
	request: import('@playwright/test').APIRequestContext,
	label: string,
	reverse: string
) {
	const created = await request.post('/api/v1/edge-types', {
		data: {
			slug: label.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
			label,
			reverse_label: reverse,
			directional: true
		}
	});
	expect(created.status(), await created.text()).toBe(201);
	const edgeType = (await created.json()) as { id: string; slug: string };
	edgeTypeIds.push(edgeType.id);
	return edgeType;
}

test('captures two items into the same box, the second in one step', async ({ page, request }) => {
	const prefix = uniqueName('Cap').replace(/\W+/g, '');
	const box = await makeItem(request, `${prefix} Box`);
	const label = uniqueName('Kept in');
	const edgeType = await makeEdgeType(request, label, 'Keeps');

	await page.goto('/');
	let dialog = await openQuickCapture(page);
	await dialog.getByPlaceholder('Name…').fill(`${prefix} First`);
	await dialog.getByLabel('Connect to').selectOption({ label: `${label}…` });
	await dialog.getByRole('combobox', { name: `${label} which item` }).click();
	await page.getByRole('option', { name: box.name }).click();
	await dialog.getByRole('button', { name: /^Saving…$|^Save$/ }).click();
	await expect(dialog).toBeHidden();

	// The relationship and the box are still chosen the next time.
	dialog = await openQuickCapture(page);
	await expect(dialog.getByLabel('Connect to')).toHaveValue(`${edgeType.slug}:forward`);
	await dialog.getByPlaceholder('Name…').fill(`${prefix} Second`);
	await dialog.getByRole('button', { name: /^Saving…$|^Save$/ }).click();
	await expect(dialog).toBeHidden();

	await expect
		.poll(async () => {
			const edges = await (await request.get(`/api/v1/edges?node_id=${box.id}&limit=50`)).json();
			return edges.length;
		})
		.toBe(2);
	const edges = await (await request.get(`/api/v1/edges?node_id=${box.id}&limit=50`)).json();
	for (const edge of edges) expect(edge.target_id).toBe(box.id);
});

test('the reverse reading puts the new item on the other end', async ({ page, request }) => {
	const prefix = uniqueName('Cap').replace(/\W+/g, '');
	const box = await makeItem(request, `${prefix} Box`);
	const label = uniqueName('Kept in');
	await makeEdgeType(request, label, 'Keeps');

	await page.goto('/');
	const dialog = await openQuickCapture(page);
	await dialog.getByPlaceholder('Name…').fill(`${prefix} Thing`);
	await dialog.getByLabel('Connect to').selectOption({ label: 'Keeps…' });
	await dialog.getByRole('combobox', { name: 'Keeps which item' }).click();
	await page.getByRole('option', { name: box.name }).click();
	await dialog.getByRole('button', { name: /^Saving…$|^Save$/ }).click();
	await expect(dialog).toBeHidden();

	await expect
		.poll(async () => {
			const edges = await (await request.get(`/api/v1/edges?node_id=${box.id}&limit=50`)).json();
			return edges.length;
		})
		.toBe(1);
	const [edge] = await (await request.get(`/api/v1/edges?node_id=${box.id}&limit=50`)).json();
	expect(edge.source_id).toBe(box.id);
});

test('a failed connection keeps the item and says so', async ({ page, request }) => {
	const prefix = uniqueName('Cap').replace(/\W+/g, '');
	const box = await makeItem(request, `${prefix} Box`);
	const label = uniqueName('Kept in');
	await makeEdgeType(request, label, 'Keeps');
	await page.route('**/api/v1/edges/batch', (route) =>
		route.request().method() === 'POST'
			? route.fulfill({
					status: 400,
					contentType: 'application/problem+json',
					body: JSON.stringify({ title: 'Bad request', status: 400, detail: 'Not today' })
				})
			: route.continue()
	);

	await page.goto('/');
	const dialog = await openQuickCapture(page);
	await dialog.getByPlaceholder('Name…').fill(`${prefix} Kept`);
	await dialog.getByLabel('Connect to').selectOption({ label: `${label}…` });
	await dialog.getByRole('combobox', { name: `${label} which item` }).click();
	await page.getByRole('option', { name: box.name }).click();
	await dialog.getByRole('button', { name: /^Saving…$|^Save$/ }).click();

	await expect(page.getByText("Saved, but couldn't connect it")).toBeVisible();
	const found = await (await request.get(`/api/v1/nodes?q=${prefix}%20Kept`)).json();
	expect(found).toHaveLength(1);
});
