import { test, expect, type APIRequestContext, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** Making an item type a subtype of another from its editor, and taking it away again (#320). */
const { cleanUp, makeItem } = ownedData();
const typeIds: string[] = [];

test.afterEach(async ({ request }) => {
	await cleanUp(request);
	// Subtypes first: a parent with subtypes cannot be deleted.
	for (const id of typeIds.splice(0).reverse()) await request.delete(`/api/v1/node-types/${id}`);
});

// The shape the editor itself writes, so opening a type does not normalise (and so change) it.
const text = (title: string) => ({ type: 'string', title, 'x-menagerist': { kind: 'text' } });
const choice = (title: string, ...options: string[]) => ({
	type: 'string',
	title,
	enum: options,
	'x-menagerist': { kind: 'choice' }
});

async function makeType(
	request: APIRequestContext,
	label: string,
	fields: Record<string, object>,
	parent?: string
) {
	const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
	const res = await request.post('/api/v1/node-types', {
		data: {
			slug,
			label,
			parent,
			// No fields at all leaves the schema out, which the editor opens without marking it edited.
			attributes_schema: Object.keys(fields).length
				? { type: 'object', properties: fields }
				: undefined
		}
	});
	expect(res.status(), await res.text()).toBe(201);
	const created = (await res.json()) as { id: string };
	typeIds.push(created.id);
	return { id: created.id, slug, label };
}

async function openEditor(page: Page, label: string) {
	await page.goto('/library/item-types');
	const row = page.getByRole('listitem').filter({ hasText: label }).first();
	await row.getByRole('button', { name: 'Edit item type' }).click();
	return page.getByRole('dialog', { name: 'Edit item type' });
}

test('a type becomes a subtype from its editor and lists the fields it gets', async ({
	page,
	request
}) => {
	const parent = await makeType(request, uniqueName('Memorabilia'), {
		condition: text('Condition')
	});
	const poster = await makeType(request, uniqueName('Poster'), { width: text('Width') });

	const dialog = await openEditor(page, poster.label);
	await dialog.getByLabel('Subtype of').selectOption({ label: parent.label });
	await expect(dialog.getByTestId('inherited-fields')).toContainText('Condition');
	await expect(dialog.getByTestId('inherited-fields')).toContainText(`From ${parent.label}`);
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(page.getByText('Item type updated')).toBeVisible();

	const saved = await (await request.get(`/api/v1/node-types/${poster.id}`)).json();
	expect(saved.parent).toBe(parent.slug);
	// The list now groups the subtype under its parent.
	await expect(page.getByRole('listitem').filter({ hasText: parent.label }).first()).toContainText(
		'1 subtype'
	);
});

test('a shared field is merged after asking, and the items keep their values', async ({
	page,
	request
}) => {
	const parent = await makeType(request, uniqueName('Memorabilia'), {
		condition: choice('Condition', 'Mint', 'Good')
	});
	const poster = await makeType(request, uniqueName('Poster'), {
		condition: choice('Condition', 'Worn'),
		width: text('Width')
	});
	const item = await makeItem(request, uniqueName('Alien one-sheet'), poster.slug);
	await request.patch(`/api/v1/nodes/${item.id}`, {
		data: { attributes: { condition: 'Worn', width: '27 in' } }
	});

	const dialog = await openEditor(page, poster.label);
	await dialog.getByLabel('Subtype of').selectOption({ label: parent.label });
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();

	const ask = page.getByRole('dialog', { name: 'Merge the shared fields?' });
	await expect(ask).toContainText('Condition');
	await ask.getByRole('button', { name: 'Merge fields' }).click();
	await expect(page.getByText('Item type updated')).toBeVisible();

	const merged = await (await request.get(`/api/v1/node-types/${parent.id}`)).json();
	expect(merged.attributes_schema.properties.condition.enum).toEqual(['Mint', 'Good', 'Worn']);
	const after = await (await request.get(`/api/v1/nodes/${item.id}`)).json();
	expect(after.attributes).toEqual({ condition: 'Worn', width: '27 in' });
});

test('removing the parent keeps its fields on the type, or hides them, as chosen', async ({
	page,
	request
}) => {
	const parent = await makeType(request, uniqueName('Memorabilia'), {
		condition: text('Condition')
	});
	const kept = await makeType(request, uniqueName('Poster'), { width: text('Width') }, parent.slug);
	const hidden = await makeType(
		request,
		uniqueName('Figure'),
		{ height: text('Height') },
		parent.slug
	);

	let dialog = await openEditor(page, kept.label);
	await dialog.getByLabel('Subtype of').selectOption({ label: 'None (a top-level item type)' });
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();
	let ask = page.getByRole('dialog', { name: new RegExp('^Make .* a top-level type') });
	await expect(ask).toContainText('Condition');
	await ask.getByRole('button', { name: 'Make top-level' }).click();
	await expect(page.getByText('Item type updated')).toBeVisible();

	const keptType = await (await request.get(`/api/v1/node-types/${kept.id}`)).json();
	expect(keptType.parent).toBeNull();
	expect(Object.keys(keptType.attributes_schema.properties)).toEqual(['width', 'condition']);

	dialog = await openEditor(page, hidden.label);
	await dialog.getByLabel('Subtype of').selectOption({ label: 'None (a top-level item type)' });
	await dialog.getByRole('button', { name: 'Save', exact: true }).click();
	ask = page.getByRole('dialog', { name: new RegExp('^Make .* a top-level type') });
	await ask.getByText('Hide the fields').click();
	await ask.getByRole('button', { name: 'Make top-level' }).click();
	await expect(page.getByText('Item type updated')).toBeVisible();

	const hiddenType = await (await request.get(`/api/v1/node-types/${hidden.id}`)).json();
	expect(hiddenType.attributes_schema.properties.condition['x-menagerist'].archived).toBe(true);
});

test('a field several subtypes share is moved up to the parent from its editor', async ({
	page,
	request
}) => {
	const parent = await makeType(request, uniqueName('Memorabilia'), {
		value: text('Value')
	});
	const poster = await makeType(
		request,
		uniqueName('Poster'),
		{ condition: choice('Condition', 'Mint', 'Good'), width: text('Width') },
		parent.slug
	);
	const print = await makeType(
		request,
		uniqueName('Print'),
		{ condition: choice('Condition', 'Fair', 'Mint') },
		parent.slug
	);
	const item = await makeItem(request, uniqueName('Alien one-sheet'), poster.slug);
	await request.patch(`/api/v1/nodes/${item.id}`, {
		data: { attributes: { condition: 'Good', width: '27 in' } }
	});

	const dialog = await openEditor(page, parent.label);
	const shared = dialog.getByTestId('subtype-shared-fields');
	await expect(shared).toContainText('Condition');
	await expect(shared).toContainText(poster.label);
	await expect(shared).toContainText(print.label);
	await shared.getByRole('button', { name: `Add Condition to ${parent.label}` }).click();
	const ask = page.getByRole('dialog', { name: `Add Condition to ${parent.label}?` });
	await ask.getByRole('button', { name: 'Add field', exact: true }).click();
	await expect(page.getByText(`Condition is now a field of ${parent.label}`)).toBeVisible();
	await expect(shared).toHaveCount(0);

	// Saved already: the parent defines it, the subtypes no longer do, and the item is unchanged.
	const moved = await (await request.get(`/api/v1/node-types/${parent.id}`)).json();
	expect(moved.attributes_schema.properties.condition.enum).toEqual(['Mint', 'Good', 'Fair']);
	const below = await (await request.get(`/api/v1/node-types/${poster.id}`)).json();
	expect(Object.keys(below.attributes_schema.properties)).toEqual(['width']);
	expect(Object.keys(below.effective_schema.properties)).toContain('condition');
	const after = await (await request.get(`/api/v1/nodes/${item.id}`)).json();
	expect(after.attributes).toEqual({ condition: 'Good', width: '27 in' });
});

test('a parent cannot become a subtype or be deleted while it has subtypes', async ({
	page,
	request
}) => {
	const parent = await makeType(request, uniqueName('Memorabilia'), {});
	const poster = await makeType(request, uniqueName('Poster'), {}, parent.slug);

	const dialog = await openEditor(page, parent.label);
	await expect(dialog.getByLabel('Subtype of')).toBeDisabled();
	await expect(dialog).toContainText(`${poster.label}`);
	await dialog.getByRole('button', { name: 'Cancel' }).click();

	const row = page.getByRole('listitem').filter({ hasText: parent.label }).first();
	await row.getByRole('button', { name: 'Delete item type' }).click();
	await expect(page.getByText(`Can't delete ${parent.label}`)).toBeVisible();
	await expect(page.getByText(`It still has subtypes: ${poster.label}`)).toBeVisible();
});
