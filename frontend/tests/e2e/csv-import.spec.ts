import { test, expect, type APIRequestContext, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * Importing a CSV into an item type: choose the file and type, match columns, preview, add.
 * Every test makes its own item type and removes the items it added, as the database is shared.
 */
const { makeItemType, cleanUp } = ownedData();

let prefix = '';
const edgeTypeIds: string[] = [];

test.afterEach(async ({ request }) => {
	const nodes = (await (await request.get('/api/v1/nodes?limit=500')).json()) as {
		id: string;
		name: string;
	}[];
	for (const node of nodes.filter((n) => n.name.startsWith(prefix))) {
		await request.delete(`/api/v1/nodes/${node.id}`);
	}
	for (const id of edgeTypeIds.splice(0)) await request.delete(`/api/v1/edge-types/${id}`);
	await cleanUp(request);
});

const SCHEMA = {
	type: 'object',
	properties: {
		position: { title: 'Position', type: 'string', 'x-menagerist': { kind: 'text' } },
		authenticated: { title: 'Authenticated', type: 'boolean', 'x-menagerist': { kind: 'boolean' } }
	}
};

async function makeType(request: APIRequestContext) {
	const type = await makeItemType(request, uniqueName('Signature'));
	const res = await request.patch(`/api/v1/node-types/${type.id}`, {
		data: { attributes_schema: SCHEMA }
	});
	expect(res.ok(), await res.text()).toBeTruthy();
	return type;
}

function csv(rows: string[]): { name: string; mimeType: string; buffer: Buffer } {
	return {
		name: 'signatures.csv',
		mimeType: 'text/csv',
		buffer: Buffer.from(['Title,Position,Authenticated', ...rows].join('\n') + '\n')
	};
}

async function chooseFileAndType(page: Page, file: ReturnType<typeof csv>, typeLabel: string) {
	await page.goto('/items/import');
	await page.locator('input[type=file]').setInputFiles(file);
	await page.getByRole('combobox', { name: 'Item type' }).click();
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('option', { name: new RegExp(typeLabel) }).click();
	await page.getByRole('button', { name: 'Next' }).click();
}

test('import a CSV into a type', async ({ page, request }) => {
	const type = await makeType(request);
	prefix = uniqueName('Sig').replace(/\W+/g, '');
	const rows = [`${prefix}A,cover,yes`, `${prefix}B,back,no`];

	await chooseFileAndType(page, csv(rows), type.label);

	// Columns are matched by name to begin with.
	await expect(page.getByLabel('Title')).toHaveValue('name');
	await expect(page.getByLabel('Position')).toHaveValue('position');

	await page.getByRole('button', { name: 'Preview' }).click();
	await expect(page.getByText('Will be added')).toBeVisible();
	await page.getByRole('button', { name: 'Add 2 items' }).click();

	await expect(page).toHaveURL(/\/items$/);
	await expect(page.getByText(`${prefix}A`).first()).toBeVisible();
});

test('a bad value stops the import and names where it is', async ({ page, request }) => {
	const type = await makeType(request);
	prefix = uniqueName('Sig').replace(/\W+/g, '');

	await chooseFileAndType(page, csv([`${prefix}A,cover,yes`, `${prefix}B,back,maybe`]), type.label);
	await page.getByRole('button', { name: 'Preview' }).click();

	await expect(page.getByText(/Row 3, Authenticated/)).toBeVisible();
	await expect(page.getByRole('button', { name: /^Add / })).toHaveCount(0);

	// Leave that column out and the rest can go ahead.
	await page.getByRole('button', { name: 'Back' }).click();
	await page.getByLabel('Authenticated').selectOption({ label: "Don't import" });
	await page.getByRole('button', { name: 'Preview' }).click();
	await expect(page.getByRole('button', { name: 'Add 2 items' })).toBeVisible();
});

test('a file the server refuses is explained on the first step', async ({ page, request }) => {
	const type = await makeType(request);
	prefix = uniqueName('Sig').replace(/\W+/g, '');
	const repeated = {
		name: 'repeated.csv',
		mimeType: 'text/csv',
		buffer: Buffer.from('Title,Title\nA,B\n')
	};

	await chooseFileAndType(page, repeated, type.label);

	await expect(page.getByRole('alert')).toContainText(/header/i);
	// The person can choose another file without reloading.
	await page.locator('input[type=file]').setInputFiles(csv([`${prefix}A,cover,yes`]));
	await page.getByRole('button', { name: 'Next' }).click();
	await expect(page.getByRole('button', { name: 'Preview' })).toBeVisible();
});

test('an Excel file in Windows-1252 is read and says so', async ({ page, request }) => {
	const type = await makeType(request);
	prefix = uniqueName('Sig').replace(/\W+/g, '');
	// 0xE9 is "é" in Windows-1252 and is not valid UTF-8.
	const excel = {
		name: 'excel.csv',
		mimeType: 'text/csv',
		buffer: Buffer.concat([
			Buffer.from(`Title,Position,Authenticated\n${prefix}Ren`),
			Buffer.from([0xe9]),
			Buffer.from(',cover,yes\n')
		])
	};

	await chooseFileAndType(page, excel, type.label);

	await expect(page.getByText('Read as Windows-1252')).toBeVisible();
	await expect(page.getByText(`${prefix}René`)).toBeVisible();
});

test('Excel date shapes are read, and the day order can be chosen', async ({ page, request }) => {
	const type = await makeItemType(request, uniqueName('Dated'));
	const res = await request.patch(`/api/v1/node-types/${type.id}`, {
		data: {
			attributes_schema: {
				type: 'object',
				properties: {
					when: { title: 'When', type: 'string', 'x-menagerist': { kind: 'partialdate' } }
				}
			}
		}
	});
	expect(res.ok(), await res.text()).toBeTruthy();
	prefix = uniqueName('Dat').replace(/\W+/g, '');
	const file = {
		name: 'dates.csv',
		mimeType: 'text/csv',
		buffer: Buffer.from(
			`Title,When\n${prefix}A,Oct-18\n${prefix}B,08/2019\n${prefix}C,03/04/2019\n`
		)
	};

	await chooseFileAndType(page, file, type.label);

	// 03/04/2019 settles nothing, so the page says it is guessing.
	await expect(page.getByLabel('Dates like 03/04/2019')).toHaveValue('day_first');
	await expect(page.getByText('day first is a guess')).toBeVisible();
	await page.getByLabel('Dates like 03/04/2019').selectOption('month_first');

	await page.getByRole('button', { name: 'Preview' }).click();
	await expect(page.getByText('Will be added')).toBeVisible();
	await page.getByRole('button', { name: 'Add 3 items' }).click();
	await expect(page).toHaveURL(/\/items$/);
});

test('a column the type has no field for is kept as each item’s own detail', async ({
	page,
	request
}) => {
	const type = await makeType(request);
	prefix = uniqueName('Sig').replace(/\W+/g, '');
	const file = {
		name: 'signatures.csv',
		mimeType: 'text/csv',
		buffer: Buffer.from(`Title,Copies\n${prefix}A,3\n${prefix}B,\n`)
	};

	await chooseFileAndType(page, file, type.label);
	await page.getByLabel('Copies').selectOption({ label: 'Keep as an extra detail' });
	// The kind is guessed from the column's values.
	await expect(page.getByLabel('Kind')).toHaveValue('number');
	await page.getByLabel('Detail name').fill('Copies signed');

	await page.getByRole('button', { name: 'Preview' }).click();
	await expect(page.getByText('Copies signed (Number)')).toBeVisible();
	await page.getByRole('button', { name: 'Add 2 items' }).click();
	await expect(page).toHaveURL(/\/items$/);

	const nodes = (await (await request.get(`/api/v1/nodes?q=${prefix}`)).json()) as {
		name: string;
		attributes: Record<string, unknown>;
		extra_schema: { properties: Record<string, { title: string }> } | null;
	}[];
	const byName = Object.fromEntries(nodes.map((n) => [n.name, n]));
	expect(byName[`${prefix}A`].attributes.copies_signed).toBe(3);
	expect(byName[`${prefix}A`].extra_schema?.properties.copies_signed.title).toBe('Copies signed');
	// An empty cell leaves the detail off that item.
	expect(byName[`${prefix}B`].extra_schema).toBeNull();
});

test('a kept column named after a detail the items already have joins it', async ({
	page,
	request
}) => {
	const type = await makeType(request);
	prefix = uniqueName('Sig').replace(/\W+/g, '');
	const existing = await request.post('/api/v1/nodes', {
		data: {
			name: `${prefix}Old`,
			type: type.slug,
			attributes: { signed: true },
			extra_schema: {
				type: 'object',
				properties: {
					signed: { title: 'Signed', type: 'boolean', 'x-menagerist': { kind: 'boolean' } }
				}
			}
		}
	});
	expect(existing.ok(), await existing.text()).toBeTruthy();
	const file = {
		name: 'signatures.csv',
		mimeType: 'text/csv',
		buffer: Buffer.from(`Title,Signed
${prefix}A,no
`)
	};

	await chooseFileAndType(page, file, type.label);
	await page.getByLabel('Signed').selectOption({ label: 'Keep as an extra detail' });
	await expect(page.getByText('Joins the Signed detail already on 1 item')).toBeVisible();
	await expect(page.getByLabel('Kind')).toHaveValue('boolean');
	await page.getByRole('button', { name: 'Preview' }).click();
	await page.getByRole('button', { name: 'Add 1 item' }).click();
	await expect(page).toHaveURL(/\/items$/);

	const fields = await (await request.get(`/api/v1/nodes/fields?type=${type.slug}`)).json();
	expect(fields).toEqual([expect.objectContaining({ key: 'signed', count: 2 })]);
});

function keyed(rows: string[]): { name: string; mimeType: string; buffer: Buffer } {
	return {
		name: 'autographs.csv',
		mimeType: 'text/csv',
		buffer: Buffer.from(['ID,Title,Position', ...rows].join('\n') + '\n')
	};
}

async function matchKeyedByID(page: Page) {
	await page.getByLabel('ID', { exact: true }).selectOption({ label: 'Keep as an extra detail' });
	await page.getByLabel('Recognise rows already imported by').selectOption({ label: 'ID' });
	await page.getByRole('button', { name: 'Preview' }).click();
}

test('a re-import keyed by ID adds only new rows and keeps deletions', async ({
	page,
	request
}) => {
	const type = await makeType(request);
	prefix = uniqueName('Auto').replace(/\W+/g, '');
	const first = [`5,${prefix} Prowse,cover`, `30,${prefix} Astley,back`];

	await chooseFileAndType(page, keyed(first), type.label);
	await matchKeyedByID(page);
	await page.getByRole('button', { name: 'Add 2 items' }).click();
	await expect(page).toHaveURL(/\/items$/);

	// The sheet grows by a row: only that one is new.
	await chooseFileAndType(page, keyed([...first, `31,${prefix} Astley again,back`]), type.label);
	await matchKeyedByID(page);
	await expect(page.getByText(`${prefix} Prowse · Already imported.`)).toBeVisible();
	await page.getByRole('button', { name: 'Add 1 item' }).click();
	await expect(page).toHaveURL(/\/items$/);

	// A row deleted after importing stays out until it is brought back.
	const nodes = (await (await request.get('/api/v1/nodes?limit=500')).json()) as {
		id: string;
		name: string;
	}[];
	const prowse = nodes.find((n) => n.name === `${prefix} Prowse`)!;
	expect((await request.delete(`/api/v1/nodes/${prowse.id}`)).ok()).toBeTruthy();

	await chooseFileAndType(page, keyed([...first, `31,${prefix} Astley again,back`]), type.label);
	await matchKeyedByID(page);
	const deleted = page.getByRole('region', { name: 'Deleted after importing' });
	await expect(deleted.getByText(`${prefix} Prowse`)).toBeVisible();
	await expect(page.getByText('You already have everything here.')).toBeVisible();

	await deleted.getByRole('checkbox', { name: `${prefix} Prowse` }).click();
	await page.getByRole('button', { name: 'Add 1 item' }).click();
	await expect(page).toHaveURL(/\/items$/);
	await expect(page.getByText(`${prefix} Prowse`).first()).toBeVisible();
});

type Edge = { id: string; source_id: string; target_id: string };

test('a column connects rows to items by name, once, and deletions stay deleted', async ({
	page,
	request
}) => {
	const type = await makeType(request);
	const event = await makeItemType(request, uniqueName('Event'));
	prefix = uniqueName('Got').replace(/\W+/g, '');
	const label = `Got at ${prefix}`;
	const made = await request.post('/api/v1/edge-types', {
		data: { slug: label.toLowerCase().replace(/[^a-z0-9]+/g, '-'), label, directional: true }
	});
	expect(made.status(), await made.text()).toBe(201);
	edgeTypeIds.push(((await made.json()) as { id: string }).id);
	const sheet = (rows: string[]) => ({
		name: 'autographs.csv',
		mimeType: 'text/csv',
		buffer: Buffer.from(['ID,Title,Position,Where', ...rows].join('\n') + '\n')
	});
	const first = [
		`5,${prefix} Prowse,cover,${prefix} eBay`,
		`30,${prefix} Astley,back,${prefix} eBay `
	];
	const connectWhere = async () => {
		await page.getByLabel('ID', { exact: true }).selectOption({ label: 'Keep as an extra detail' });
		await page
			.getByLabel('Where', { exact: true })
			.selectOption({ label: 'Connect to an item by name' });
		await page.getByLabel('Connection type').selectOption({ label });
		await page.getByRole('combobox', { name: "The other item's type for Where" }).click();
		await page.getByPlaceholder('Search item types…').fill(event.label);
		await page.getByRole('option', { name: new RegExp(event.label) }).click();
		await page.getByLabel('Recognise rows already imported by').selectOption({ label: 'ID' });
		await page.getByRole('button', { name: 'Preview' }).click();
	};
	const nodes = async () =>
		(await (await request.get('/api/v1/nodes?limit=500')).json()) as { id: string; name: string }[];
	const edgesOf = async (id: string) =>
		(await (await request.get(`/api/v1/edges?node_id=${id}`)).json()) as Edge[];

	// Two rows name the same place, one with a trailing space: one event is made.
	await chooseFileAndType(page, sheet(first), type.label);
	await connectWhere();
	await expect(
		page.getByText(`New items from connected columns, with just their names: ${prefix} eBay.`)
	).toBeVisible();
	await page.getByRole('button', { name: 'Add 3 items' }).click();
	await expect(page).toHaveURL(/\/items$/);
	const all = await nodes();
	const ebay = all.filter((n) => n.name.toLowerCase() === `${prefix} ebay`.toLowerCase());
	expect(ebay.map((n) => n.name)).toEqual([`${prefix} eBay`]);
	expect(await edgesOf(ebay[0].id)).toHaveLength(2);

	// One connection deleted stays deleted; the new row's connection is made.
	const prowse = all.find((n) => n.name === `${prefix} Prowse`)!;
	const gone = (await edgesOf(ebay[0].id)).find((e) => e.source_id === prowse.id)!;
	expect((await request.delete(`/api/v1/edges/${gone.id}`)).ok()).toBeTruthy();

	await chooseFileAndType(
		page,
		sheet([...first, `31,${prefix} Astley again,back,${prefix} ebay`]),
		type.label
	);
	await connectWhere();
	const deleted = page.getByRole('region', { name: 'Deleted after importing' });
	await expect(deleted.getByText(`${prefix} Prowse to ${prefix} eBay`)).toBeVisible();
	await page.getByRole('button', { name: 'Add 1 item' }).click();
	await expect(page).toHaveURL(/\/items$/);
	const after = await edgesOf(ebay[0].id);
	expect(after).toHaveLength(2);
	expect(after.some((e) => e.source_id === prowse.id)).toBe(false);
});
