import { test, expect, type APIRequestContext } from './fixtures';
import { chooseItemType, ownedData, uniqueName } from './helpers';

/** An item type may be a subtype of another and uses its parent's fields (#320). */
const { cleanUp, makeItem } = ownedData();
const typeIds: string[] = [];

test.afterEach(async ({ request }) => {
	await cleanUp(request);
	// Subtypes first: a parent with subtypes cannot be deleted.
	for (const id of typeIds.splice(0).reverse()) await request.delete(`/api/v1/node-types/${id}`);
});

const field = (title: string) => ({ type: 'string', title });

async function makeType(
	request: APIRequestContext,
	label: string,
	fields: Record<string, { type: string; title: string }>,
	parent?: string
): Promise<{ id: string; slug: string; label: string }> {
	const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
	const res = await request.post('/api/v1/node-types', {
		data: {
			slug,
			label,
			parent,
			attributes_schema: { type: 'object', properties: fields }
		}
	});
	expect(res.status(), await res.text()).toBe(201);
	const created = (await res.json()) as { id: string };
	typeIds.push(created.id);
	return { id: created.id, slug, label };
}

test('a subtype`s item form has its parent`s fields and its own', async ({ page, request }) => {
	const parent = await makeType(request, uniqueName('Memorabilia'), {
		condition: field('Condition')
	});
	const poster = await makeType(
		request,
		uniqueName('Poster'),
		{ width: field('Width') },
		parent.slug
	);

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Alien one-sheet'));
	await chooseItemType(page, poster.label);

	await page.getByLabel('Condition').fill('Near mint');
	await page.getByLabel('Width').fill('27 inches');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('Near mint')).toBeVisible();
	await expect(page.getByText('27 inches')).toBeVisible();
});

test('an item of the parent type itself has only the parent`s fields', async ({
	page,
	request
}) => {
	const parent = await makeType(request, uniqueName('Memorabilia'), {
		condition: field('Condition')
	});
	await makeType(request, uniqueName('Poster'), { width: field('Width') }, parent.slug);

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Loose ticket'));
	await chooseItemType(page, parent.label);

	await expect(page.getByLabel('Condition')).toBeVisible();
	await expect(page.getByLabel('Width')).toHaveCount(0);
});

test('the type picker groups a family under its parent and shows a subtype with it', async ({
	page,
	request
}) => {
	const parent = await makeType(request, uniqueName('Memorabilia'), {});
	const poster = await makeType(request, uniqueName('Poster'), {}, parent.slug);
	const figure = await makeType(request, uniqueName('Figure'), {}, parent.slug);
	await makeItem(request, uniqueName('Alien one-sheet'), poster.slug);

	await page.goto('/items/new');
	await page.getByRole('combobox', { name: 'Item type' }).click();

	// A subtype in use is listed on its own with its parent; the rest sit under the parent's name.
	const list = page.getByRole('listbox');
	await expect(list.getByRole('group', { name: parent.label })).toContainText(figure.label);
	await expect(
		list.getByRole('option', { name: new RegExp(`${parent.label}.*${poster.label}`) })
	).toBeVisible();

	await page.getByRole('option', { name: new RegExp(figure.label) }).click();
	const trigger = page.getByRole('combobox', { name: 'Item type' });
	await expect(trigger).toContainText(parent.label);
	await expect(trigger).toContainText(figure.label);
});

test('a subtype`s items show its parent in the type row and keep just its name on cards', async ({
	page,
	request
}) => {
	const parent = await makeType(request, uniqueName('Memorabilia'), {});
	const poster = await makeType(request, uniqueName('Poster'), {}, parent.slug);
	const name = uniqueName('Alien one-sheet');
	await makeItem(request, name, poster.slug);

	await page.goto('/items');
	await expect(page.getByText(`${parent.label} › ${poster.label}`)).toBeVisible();
	const card = page.getByRole('link', { name: new RegExp(name) }).first();
	await expect(card).toContainText(poster.label);
	await expect(card.getByText(`, a subtype of ${parent.label}`)).toBeAttached();
});

test('searching the item types for a parent shows its subtypes, and for a subtype its parent', async ({
	page,
	request
}) => {
	const parent = await makeType(request, uniqueName('Memorabilia'), {});
	const poster = await makeType(request, uniqueName('Poster'), {}, parent.slug);
	const stub = await makeType(request, uniqueName('Stub'), {}, parent.slug);
	// The search box only shows once the list is long enough to need it.
	const others: string[] = [];
	for (let i = 0; i < 8; i += 1) {
		others.push((await makeType(request, uniqueName(`Other ${i}`), {})).label);
	}

	await page.goto('/library/item-types');
	const search = page.getByPlaceholder('Search item types…');
	// A subtype's row also names its parent for a screen reader, so find a row by its own checkbox.
	const row = (label: string) =>
		page.getByRole('checkbox', { name: `Select ${label}`, exact: true });

	await search.fill(parent.label);
	await expect(row(parent.label)).toHaveCount(1);
	await expect(row(poster.label)).toHaveCount(1);
	await expect(row(stub.label)).toHaveCount(1);
	await expect(row(others[0])).toHaveCount(0);

	await search.fill(poster.label);
	await expect(row(poster.label)).toHaveCount(1);
	await expect(row(parent.label)).toHaveCount(1);
	// The parent's other subtype stays out: it did not match.
	await expect(row(stub.label)).toHaveCount(0);
});

test('a parent with subtypes cannot be deleted, and the list of its subtypes shows them', async ({
	request
}) => {
	const parent = await makeType(request, uniqueName('Memorabilia'), {
		condition: field('Condition')
	});
	const poster = await makeType(
		request,
		uniqueName('Poster'),
		{ width: field('Width') },
		parent.slug
	);

	const refused = await request.delete(`/api/v1/node-types/${parent.id}`);
	expect(refused.status()).toBe(409);
	const subtypes = await (await request.get(`/api/v1/node-types/${parent.id}/subtypes`)).json();
	expect((subtypes as { slug: string }[]).map((t) => t.slug)).toEqual([poster.slug]);
});
