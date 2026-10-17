import { test, expect, type APIRequestContext, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * Advanced search on the Items page: the Filters panel, the shareable `?f=` link, history and
 * keyboard use. The database is shared, so every test creates its own item type (conditions name
 * a type and a field, so they only ever match that type's items) and removes it afterwards.
 */
test.describe.configure({ mode: 'serial' });

const { makeItem, makeItemType, cleanUp } = ownedData();

// Items made with attributes are tracked here; they go before their type does.
const seededItemIds: string[] = [];

test.afterEach(async ({ request }) => {
	for (const id of seededItemIds.splice(0)) await request.delete(`/api/v1/node/${id}`);
	await cleanUp(request);
});

type Tool = { id: string; slug: string; label: string };

const WEIGHT_AND_GRADE = {
	type: 'object',
	properties: {
		weight: { title: 'Weight', type: 'number' },
		grade: { title: 'Grade', type: 'string', enum: ['a', 'b'] }
	}
};

/** An item type with a number field "Weight" and a choice field "Grade". */
async function makeTool(request: APIRequestContext): Promise<Tool> {
	const tool = await makeItemType(request, uniqueName('Tool'));
	const res = await request.patch(`/api/v1/node-type/${tool.id}`, {
		data: { attributes_schema: WEIGHT_AND_GRADE }
	});
	expect(res.ok(), await res.text()).toBeTruthy();
	return tool;
}

/** Seeds A (2, a), B (5, a), C (8, b) and D (no attributes); returns the unique item names. */
async function seedItems(request: APIRequestContext, tool: Tool) {
	const suffix = uniqueName('x').replace(/\W+/g, '');
	const names = {
		a: `Anvil${suffix}`,
		b: `Bolt${suffix}`,
		c: `Chisel${suffix}`,
		d: `Drill${suffix}`
	};
	const seeds: [string, Record<string, unknown>][] = [
		[names.a, { weight: 2, grade: 'a' }],
		[names.b, { weight: 5, grade: 'a' }],
		[names.c, { weight: 8, grade: 'b' }],
		[names.d, {}]
	];
	for (const [name, attributes] of seeds) {
		const res = await request.post('/api/v1/node', {
			data: { name, type: tool.slug, attributes }
		});
		expect(res.status(), await res.text()).toBe(201);
		const created = (await res.json()) as { id: string };
		seededItemIds.push(created.id);
	}
	return names;
}

const itemLink = (page: Page, name: string) => page.getByRole('link', { name: new RegExp(name) });
const filtersButton = (page: Page) => page.getByRole('button', { name: /^Filters/ });
const filtersDialog = (page: Page) => page.getByRole('dialog', { name: 'Filters' });

/** Opens the panel with the button and waits for the item types (the field choices) to load. */
async function openFilters(page: Page) {
	await filtersButton(page).click();
	const dialog = filtersDialog(page);
	await expect(dialog).toBeVisible();
	return dialog;
}

/** Picks a field in a row's searchable picker: types the type and field name, then clicks the one match. */
async function pickField(page: Page, n: number, field: string) {
	const [group, label] = field.includes(' › ') ? field.split(' › ') : [undefined, field];
	await filtersDialog(page)
		.getByRole('combobox', { name: `Condition ${n}, field` })
		.click();
	await page.getByPlaceholder('Search fields…').fill(group ? `${group} ${label}` : label);
	await page.getByRole('option', { name: label, exact: true }).click();
	await expect(page.getByRole('listbox')).toHaveCount(0);
}

/** Fills a condition row: the field, the operator and a value typed into a plain input. */
async function fillRow(
	page: Page,
	n: number,
	row: { field: string; operator: string; value?: string }
) {
	const dialog = filtersDialog(page);
	await pickField(page, n, row.field);
	await dialog.getByLabel(`Condition ${n}, operator`).selectOption({ label: row.operator });
	if (row.value !== undefined) await dialog.getByLabel(`Condition ${n}, value`).fill(row.value);
}

test('filter items by a field, move through history and share the link', async ({
	page,
	request
}) => {
	const tool = await makeTool(request);
	const names = await seedItems(request, tool);

	await page.goto('/items');
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	await expect(itemLink(page, names.a)).toBeVisible();

	// The `f` shortcut must not fire while typing in an input.
	const searchBox = page.getByPlaceholder('Search your items…');
	await searchBox.click();
	await page.keyboard.type('f');
	await expect(searchBox).toHaveValue('f');
	await expect(filtersDialog(page)).toHaveCount(0);
	await searchBox.fill('');
	await page.locator('body').click({ position: { x: 5, y: 5 } });

	// Outside an input it opens the panel.
	await page.keyboard.press('f');
	const dialog = filtersDialog(page);
	await expect(dialog).toBeVisible();

	await fillRow(page, 1, {
		field: `${tool.label} › Weight`,
		operator: 'is at least',
		value: '5'
	});

	await dialog.getByRole('button', { name: 'Done' }).click();
	await expect(dialog).toHaveCount(0);

	await expect(itemLink(page, names.b)).toBeVisible();
	await expect(itemLink(page, names.c)).toBeVisible();
	await expect(itemLink(page, names.a)).toHaveCount(0);
	await expect(itemLink(page, names.d)).toHaveCount(0);
	await expect(page.getByText('2 items', { exact: true })).toBeVisible();
	await expect(page.getByRole('list', { name: 'Active filters' })).toContainText('Weight');
	await expect(filtersButton(page)).toHaveAccessibleName(/Filters\s*1\s*condition/);
	await expect(page).toHaveURL(/[?&]f=/);

	// One editing session is one history entry: Back leaves the filter, Forward restores it.
	await page.goBack();
	await expect(page).not.toHaveURL(/[?&]f=/);
	await expect(itemLink(page, names.a)).toBeVisible();
	await page.goForward();
	await expect(page).toHaveURL(/[?&]f=/);
	await expect(itemLink(page, names.a)).toHaveCount(0);
	await expect(itemLink(page, names.b)).toBeVisible();

	// The link carries the filter: a reload and a fresh visit both show the same results.
	const url = page.url();
	await page.reload();
	await expect(itemLink(page, names.b)).toBeVisible();
	await expect(itemLink(page, names.a)).toHaveCount(0);
	await page.goto('/items');
	await expect(itemLink(page, names.a)).toBeVisible();
	await page.goto(url);
	await expect(itemLink(page, names.c)).toBeVisible();
	await expect(itemLink(page, names.a)).toHaveCount(0);
});

test('a group can match any, and a stale condition shows a warning', async ({ page, request }) => {
	const tool = await makeTool(request);
	const names = await seedItems(request, tool);

	await page.goto('/items');
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	const dialog = await openFilters(page);

	// Condition 1: weight at most 2. Condition 2: grade is b. Matching "any" lists A and C.
	await fillRow(page, 1, { field: `${tool.label} › Weight`, operator: 'is at most', value: '2' });
	await dialog.getByRole('button', { name: 'Add condition' }).first().click();
	await fillRow(page, 2, { field: `${tool.label} › Grade`, operator: 'is' });
	await dialog.getByRole('button', { name: 'Condition 2, value' }).click();
	await page.getByRole('option', { name: 'b', exact: true }).click();

	// Both must hold by default, which matches nothing; "any" widens it.
	await expect(page.getByText('No items match these filters')).toBeVisible();
	const groupToggle = dialog.getByRole('group', { name: 'All conditions: match all or any' });
	await groupToggle.getByRole('button', { name: 'any' }).click();
	await expect(groupToggle.getByRole('button', { name: 'any' })).toHaveAttribute(
		'aria-pressed',
		'true'
	);
	await dialog.getByRole('button', { name: 'Done' }).click();

	await expect(itemLink(page, names.a)).toBeVisible();
	await expect(itemLink(page, names.c)).toBeVisible();
	await expect(itemLink(page, names.b)).toHaveCount(0);
	await expect(page.getByText('2 items', { exact: true })).toBeVisible();
	await expect(page.getByText('This field no longer exists, so nothing matches.')).toHaveCount(0);
	const url = page.url();

	// Remove the Weight field through the API; the saved link keeps naming it.
	const patched = await request.patch(`/api/v1/node-type/${tool.id}`, {
		data: {
			attributes_schema: {
				type: 'object',
				properties: { grade: WEIGHT_AND_GRADE.properties.grade }
			}
		}
	});
	expect(patched.ok(), await patched.text()).toBeTruthy();

	await page.goto(url);
	await expect(page.getByText(/no longer exists|is archived/).first()).toBeVisible();
	// The stale condition matches nothing, the other one still applies.
	await expect(itemLink(page, names.c)).toBeVisible();
	await expect(itemLink(page, names.a)).toHaveCount(0);
	await expect(page.getByRole('list', { name: 'Active filters' })).toBeVisible();
});

test('the builder works by keyboard alone', async ({ page, request }) => {
	const tool = await makeTool(request);
	const names = await seedItems(request, tool);

	await page.goto('/items');
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	await expect(itemLink(page, names.a)).toBeVisible();

	// Open with Enter from the focused button.
	await filtersButton(page).focus();
	await page.keyboard.press('Enter');
	const dialog = filtersDialog(page);
	await expect(dialog).toBeVisible();

	// With no conditions yet, focus lands on the first row's field picker.
	const field = dialog.getByRole('combobox', { name: 'Condition 1, field' });
	await expect(field).toBeFocused();
	await expect(field).toHaveText(/Choose what to filter on/);
	await expect(field).toHaveAttribute('aria-expanded', 'false');

	// Escape closes the list and returns focus to the picker.
	await page.keyboard.press('ArrowDown');
	await expect(field).toHaveAttribute('aria-expanded', 'true');
	await expect(page.getByPlaceholder('Search fields…')).toBeFocused();
	await page.keyboard.press('Escape');
	await expect(field).toHaveAttribute('aria-expanded', 'false');
	await expect(field).toBeFocused();
	await expect(dialog).toBeVisible();

	// Enter opens it, typing searches (also by type name), arrows move and Enter selects.
	await page.keyboard.press('Enter');
	await expect(page.getByPlaceholder('Search fields…')).toBeFocused();
	await expect(page.getByRole('option', { name: 'Weight', exact: true })).toBeVisible();
	await page.keyboard.type(`${tool.label} we`);
	await expect(page.getByRole('listbox').getByRole('option')).toHaveCount(1);
	await page.keyboard.press('ArrowDown');
	await page.keyboard.press('Enter');
	await expect(field).toHaveText(`${tool.label} › Weight`);
	await expect(field).toBeFocused();

	// Space opens it again with the current choice ticked. Typing highlights the first match, so
	// Enter takes it (Grade comes before Weight).
	await page.keyboard.press('Space');
	await expect(page.getByPlaceholder('Search fields…')).toBeFocused();
	await expect(page.getByRole('option', { name: 'Weight', exact: true })).toHaveAttribute(
		'data-checked',
		'true'
	);
	await page.keyboard.type(tool.label);
	const options = page.getByRole('listbox').getByRole('option');
	await expect(options).toHaveText(['Grade', 'Weight']);
	await page.keyboard.press('Enter');
	await expect(field).toHaveText(`${tool.label} › Grade`);

	// An arrow key moves the highlight to the next match.
	await page.keyboard.press('Enter');
	await expect(page.getByPlaceholder('Search fields…')).toBeFocused();
	await page.keyboard.type(tool.label);
	await expect(options).toHaveCount(2);
	await page.keyboard.press('ArrowDown');
	await page.keyboard.press('Enter');
	await expect(field).toHaveText(`${tool.label} › Weight`);

	await page.keyboard.press('Tab');
	const operator = dialog.getByLabel('Condition 1, operator');
	await expect(operator).toBeFocused();
	await page.keyboard.type('is at least');
	await expect(operator).toHaveValue('>=');

	// The row's remove button sits between the operator and the value.
	await page.keyboard.press('Tab');
	await expect(dialog.getByRole('button', { name: 'Remove condition 1' })).toBeFocused();
	await page.keyboard.press('Tab');
	const value = dialog.getByLabel('Condition 1, value');
	await expect(value).toBeFocused();
	await page.keyboard.type('5');
	await expect(page).toHaveURL(/[?&]f=/);
	await expect(itemLink(page, names.a)).toHaveCount(0);

	// Add a second condition with Enter, then remove it with Enter; focus stays in the panel.
	const add = dialog.getByRole('button', { name: 'Add condition' }).first();
	await add.focus();
	await page.keyboard.press('Enter');
	await expect(dialog.getByLabel('Condition 2, field')).toBeFocused();
	await dialog.getByRole('button', { name: 'Remove condition 2' }).focus();
	await page.keyboard.press('Enter');
	await expect(dialog.getByLabel('Condition 2, field')).toHaveCount(0);
	await expect(dialog.getByLabel('Condition 1, field')).toBeFocused();

	// Remove the last condition too: the filter is cleared.
	await dialog.getByRole('button', { name: 'Remove condition 1' }).focus();
	await page.keyboard.press('Enter');
	await expect(dialog.getByLabel('Condition 1, field')).toBeFocused();
	await expect(itemLink(page, names.a)).toBeVisible();

	// Escape closes the panel and gives focus back to the Filters button.
	await page.keyboard.press('Escape');
	await expect(dialog).toHaveCount(0);
	await expect(filtersButton(page)).toBeFocused();
});

test('an invalid filter link shows a message and the page still lists items', async ({
	page,
	request
}) => {
	const item = await makeItem(request, uniqueName('Plain item'));

	await page.goto('/items?f=this-is-not-a-filter');
	await expect(page.getByText("That filter link isn't valid.")).toBeVisible();
	await expect(page).not.toHaveURL(/[?&]f=/);
	await expect(page.getByRole('link', { name: new RegExp(item.name) })).toBeVisible();
	await expect(filtersButton(page)).toBeVisible();
});

test('the count line stays while more items load', async ({ page, request }) => {
	test.setTimeout(120_000);
	const tool = await makeTool(request);
	const total = 55;
	const suffix = uniqueName('p').replace(/\W+/g, '');
	for (let start = 0; start < total; start += 10) {
		await Promise.all(
			Array.from({ length: Math.min(10, total - start) }, async (_, i) => {
				const res = await request.post('/api/v1/node', {
					data: {
						name: `Pile${suffix}-${String(start + i).padStart(3, '0')}`,
						type: tool.slug,
						attributes: { weight: start + i }
					}
				});
				expect(res.status()).toBe(201);
				seededItemIds.push(((await res.json()) as { id: string }).id);
			})
		);
	}

	await page.goto('/items');
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	await openFilters(page);
	await fillRow(page, 1, { field: `${tool.label} › Weight`, operator: 'is at least', value: '0' });
	await filtersDialog(page).getByRole('button', { name: 'Done' }).click();

	const countLine = page.getByText(`${total} items`, { exact: true });
	await expect(countLine).toBeVisible();
	const piles = page.getByRole('link', { name: new RegExp(`Pile${suffix}`) });
	await expect(piles).toHaveCount(50);

	// Scroll the last card into view until the next page is in; the count line must not blink out on the way.
	await expect
		.poll(
			async () => {
				await piles.last().scrollIntoViewIfNeeded();
				await expect(countLine).toBeVisible();
				return piles.count();
			},
			{ timeout: 20_000 }
		)
		.toBe(total);
	await expect(countLine).toBeVisible();
});

test('filter items by a per-item field, and never match a type field with the same key', async ({
	page,
	request
}) => {
	const suffix = uniqueName('k').replace(/\W+/g, '');
	const key = `shelf${suffix}`;
	const label = `Shelf${suffix}`;
	const overlay = {
		type: 'object',
		properties: { [key]: { title: label, type: 'string', 'x-menagerist': { kind: 'text' } } }
	};
	const names = { a: `Atlas${suffix}`, b: `Brief${suffix}`, c: `Clash${suffix}` };

	async function seed(data: Record<string, unknown>) {
		const res = await request.post('/api/v1/node', { data });
		expect(res.status(), await res.text()).toBe(201);
		seededItemIds.push(((await res.json()) as { id: string }).id);
	}

	// Two items carry the field themselves; a third is of a type that defines the same key.
	await seed({ name: names.a, extra_schema: overlay, attributes: { [key]: 'oak' } });
	await seed({ name: names.b, extra_schema: overlay, attributes: { [key]: 'pine' } });
	const clashType = await makeItemType(request, uniqueName('Clash'));
	const patched = await request.patch(`/api/v1/node-type/${clashType.id}`, {
		data: {
			attributes_schema: {
				type: 'object',
				properties: { [key]: { title: label, type: 'string' } }
			}
		}
	});
	expect(patched.ok(), await patched.text()).toBeTruthy();
	await seed({ name: names.c, type: clashType.slug, attributes: { [key]: 'oak' } });

	await page.goto('/items');
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	await expect(itemLink(page, names.c)).toBeVisible();
	const dialog = await openFilters(page);

	await dialog.getByRole('combobox', { name: 'Condition 1, field' }).click();
	await page.getByPlaceholder('Search fields…').fill(`Per-item fields ${label}`);
	await page.getByRole('option', { name: label, exact: true }).click();
	await dialog.getByLabel('Condition 1, operator').selectOption({ label: 'is' });
	await dialog.getByLabel('Condition 1, value').fill('oak');
	await dialog.getByRole('button', { name: 'Done' }).click();
	await expect(dialog).toHaveCount(0);

	// Only the item whose own field matches is listed: not B (pine), not C (type field, same value).
	await expect(itemLink(page, names.a)).toBeVisible();
	await expect(itemLink(page, names.b)).toHaveCount(0);
	await expect(itemLink(page, names.c)).toHaveCount(0);
	await expect(page.getByText('1 item', { exact: true })).toBeVisible();
	await expect(page).toHaveURL(/[?&]f=/);

	await page.reload();
	await expect(itemLink(page, names.a)).toBeVisible();
	await expect(itemLink(page, names.b)).toHaveCount(0);
	await expect(itemLink(page, names.c)).toHaveCount(0);
	await expect(page.getByRole('list', { name: 'Active filters' })).toContainText(label);
});

test('filter items by a per-item number field with at least', async ({ page, request }) => {
	const suffix = uniqueName('n').replace(/\W+/g, '');
	const key = `size${suffix}`;
	const label = `Size${suffix}`;
	const overlay = {
		type: 'object',
		properties: { [key]: { title: label, type: 'number', 'x-menagerist': { kind: 'number' } } }
	};
	const names = { small: `Small${suffix}`, big: `Big${suffix}` };
	for (const [name, size] of [
		[names.small, 3],
		[names.big, 12]
	] as const) {
		const res = await request.post('/api/v1/node', {
			data: { name, extra_schema: overlay, attributes: { [key]: size } }
		});
		expect(res.status(), await res.text()).toBe(201);
		seededItemIds.push(((await res.json()) as { id: string }).id);
	}

	await page.goto('/items');
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	const dialog = await openFilters(page);
	await dialog.getByRole('combobox', { name: 'Condition 1, field' }).click();
	await page.getByPlaceholder('Search fields…').fill(`Per-item fields ${label}`);
	await page.getByRole('option', { name: label, exact: true }).click();
	await dialog.getByLabel('Condition 1, operator').selectOption({ label: 'is at least' });
	await dialog.getByLabel('Condition 1, value').fill('10');
	await dialog.getByRole('button', { name: 'Done' }).click();
	await expect(dialog).toHaveCount(0);

	await expect(itemLink(page, names.big)).toBeVisible();
	await expect(itemLink(page, names.small)).toHaveCount(0);
	await expect(page.getByRole('list', { name: 'Active filters' })).toContainText(
		`Per-item field › ${label}`
	);
});

test('a per-item condition on a field no item has says so', async ({ page }) => {
	const query = {
		v: 1,
		where: {
			op: 'and',
			children: [
				{
					kind: 'field',
					field_kind: 'text',
					key: `nothing${uniqueName('n').replace(/\W+/g, '')}`,
					op: '=',
					value: 'x'
				}
			]
		},
		sort: []
	};
	const token = Buffer.from(JSON.stringify(query)).toString('base64url');

	await page.goto(`/items?f=${token}`);
	await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible();
	await openFilters(page);
	await expect(filtersDialog(page).getByText('No item has this field.')).toBeVisible();
});
