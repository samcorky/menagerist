import { test, expect, type APIRequestContext } from './fixtures';
import { chooseItemType, ownedData, uniqueName } from './helpers';

/** An item type may be a subtype of another and uses its parent's fields (#320). */
const { cleanUp } = ownedData();
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
