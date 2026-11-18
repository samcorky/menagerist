import { test, expect, type APIRequestContext, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * Importing a CSV into an item type: choose the file and type, match columns, preview, add.
 * Every test makes its own item type and removes the items it added, as the database is shared.
 */
const { makeItemType, cleanUp } = ownedData();

let prefix = '';

test.afterEach(async ({ request }) => {
	const nodes = (await (await request.get('/api/v1/nodes?limit=500')).json()) as {
		id: string;
		name: string;
	}[];
	for (const node of nodes.filter((n) => n.name.startsWith(prefix))) {
		await request.delete(`/api/v1/nodes/${node.id}`);
	}
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
