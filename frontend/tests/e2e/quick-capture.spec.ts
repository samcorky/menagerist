import { test, expect } from './fixtures';
import { chooseItemType, createItemType, openQuickCapture, uniqueName } from './helpers';

test('captures an item from the quick capture dialog', async ({ page }) => {
	const name = uniqueName('Quick capture item');

	await page.goto('/');
	const dialog = await openQuickCapture(page);

	await dialog.getByPlaceholder('Name…').fill(name);
	await dialog.getByRole('button', { name: /^Saving…$|^Save$/ }).click();
	await expect(dialog).toBeHidden();

	await page.goto('/items');
	await page.getByPlaceholder('Search your items…').fill(name);
	await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
});

test.describe('quick-capture fields', () => {
	test("shows the type's quick-capture fields and saves them", async ({ page }) => {
		const { label } = await createItemType(page, {
			label: uniqueName('Capture book'),
			fields: [{ label: 'ISBN', capture: true }, { label: 'Notes' }]
		});
		const name = uniqueName('Captured book');

		await page.goto('/');
		const dialog = await openQuickCapture(page);
		await dialog.getByPlaceholder('Name…').fill(name);
		await chooseItemType(page, label);
		await expect(dialog.getByLabel('Notes')).toHaveCount(0);
		await dialog.getByLabel('ISBN').fill('9780141036144');
		await dialog.getByRole('button', { name: /^Saving…$|^Save$/ }).click();
		await expect(dialog).toBeHidden();

		await page.goto('/items');
		await page.getByPlaceholder('Search your items…').fill(name);
		await page.getByText(name, { exact: true }).first().click();
		await expect(page.getByText('9780141036144')).toBeVisible();
	});

	test('a type with no quick-capture fields shows no extra inputs', async ({ page }) => {
		const { label } = await createItemType(page, {
			label: uniqueName('Plain type'),
			fields: [{ label: 'Notes' }]
		});

		await page.goto('/');
		const dialog = await openQuickCapture(page);
		await chooseItemType(page, label);
		await expect(dialog.getByLabel('Notes')).toHaveCount(0);
		await expect(dialog.getByText('Details')).toHaveCount(0);
	});

	test('changing the type drops values typed for the old one', async ({ page }) => {
		const { label: plain } = await createItemType(page, { label: uniqueName('Plain type') });
		const { label: book } = await createItemType(page, {
			label: uniqueName('Capture book'),
			fields: [{ label: 'ISBN', capture: true }]
		});

		await page.goto('/');
		const dialog = await openQuickCapture(page);
		await chooseItemType(page, book);
		await dialog.getByLabel('ISBN').fill('123');
		await chooseItemType(page, plain);
		await expect(dialog.getByLabel('ISBN')).toHaveCount(0);
		await chooseItemType(page, book);
		await expect(dialog.getByLabel('ISBN')).toHaveValue('');
	});

	test('the full form keeps quick-capture values', async ({ page }) => {
		const { label } = await createItemType(page, {
			label: uniqueName('Capture book'),
			fields: [
				{ label: 'ISBN', capture: true },
				{ label: 'Score', kind: 'rating', capture: true }
			]
		});

		await page.goto('/');
		const dialog = await openQuickCapture(page);
		await dialog.getByPlaceholder('Name…').fill(uniqueName('Handed over'));
		await chooseItemType(page, label);
		await dialog.getByLabel('ISBN').fill('9780141036144');
		await dialog
			.getByRole('radiogroup', { name: 'Score' })
			.getByRole('radio', { name: '4 stars' })
			.click();
		await dialog.getByRole('button', { name: 'Use full form →' }).click();

		await expect(page).toHaveURL(/\/items\/new/);
		await expect(page.getByLabel('ISBN')).toHaveValue('9780141036144');
		await expect(
			page.getByRole('radiogroup', { name: 'Score' }).getByRole('radio', { name: '4 stars' })
		).toBeChecked();
	});

	test("a field's actions sit on its row, not below its chips", async ({ page }) => {
		test.skip((page.viewportSize()?.width ?? 0) < 640, 'actions stack under the field on a phone');
		await createItemType(page, {
			label: uniqueName('Aligned'),
			fields: [{ label: 'ISBN', capture: true }]
		});
		await page.getByRole('button', { name: 'Edit item type' }).first().click();
		const form = page
			.locator('form')
			.filter({ has: page.getByRole('button', { name: /^Saving…$|^Save$/ }) });
		const label = await form.getByLabel('Field label').first().boundingBox();
		const menu = await form
			.getByRole('button', { name: 'More field actions' })
			.first()
			.boundingBox();
		const middle = (box: { y: number; height: number }) => box.y + box.height / 2;
		expect(Math.abs(middle(label!) - middle(menu!))).toBeLessThan(3);
	});
});
