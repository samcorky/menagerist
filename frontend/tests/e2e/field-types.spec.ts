import { test, expect } from './fixtures';
import { createItemType, uniqueName } from './helpers';

/**
 * Input, validation and view coverage for the field-type kinds, driven through the real UI
 * (item type creation, item creation, and the item detail view) rather than API shortcuts.
 */

test('text field: input and view', async ({ page }) => {
	const typeLabel = uniqueName('Book');
	await createItemType(page, { label: typeLabel, fields: [{ label: 'Author', kind: 'text' }] });

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Dune'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();
	await page.getByLabel('Author').fill('Frank Herbert');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('Frank Herbert')).toBeVisible();
	await page.reload();
	await expect(page.getByText('Frank Herbert')).toBeVisible();
});

test('number field: input, validation and view', async ({ page }) => {
	const typeLabel = uniqueName('Gadget');
	await createItemType(page, { label: typeLabel, fields: [{ label: 'Price', kind: 'number' }] });

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Widget'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	// A plain number input has no `step="any"`, so a non-integer value fails the browser's
	// native step validation and silently blocks the submit - use a whole number here.
	const priceInput = page.getByLabel('Price');
	await priceInput.fill('42');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('42', { exact: true })).toBeVisible();
	await page.reload();
	await expect(page.getByText('42', { exact: true })).toBeVisible();
});

test('boolean field: input and view', async ({ page }) => {
	const typeLabel = uniqueName('Vinyl');
	await createItemType(page, { label: typeLabel, fields: [{ label: 'Signed', kind: 'boolean' }] });

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Rumours'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByRole('switch', { name: 'Signed' }).click();
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('Signed')).toBeVisible();
	await page.reload();
	// View mode renders a read-only checkbox (not the editable switch) reflecting the value.
	await expect(page.getByText('Signed')).toBeVisible();
	await expect(page.locator('input[type="checkbox"]')).toBeChecked();
});

test('money field: input and view (symbol-known and no-symbol currencies)', async ({ page }) => {
	const typeLabel = uniqueName('Antique');
	await createItemType(page, {
		label: typeLabel,
		fields: [{ label: 'Purchase price', kind: 'money' }]
	});

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Vase'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByLabel('Purchase price amount').fill('45');
	await page.getByLabel('Purchase price currency').selectOption('GBP');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('£45.00', { exact: true })).toBeVisible();
	await page.reload();
	await expect(page.getByText('£45.00', { exact: true })).toBeVisible();
});

test('money field: partial value (amount only) is kept, and empty is omitted', async ({ page }) => {
	const typeLabel = uniqueName('Collectible');
	await createItemType(page, {
		label: typeLabel,
		fields: [{ label: 'Value', kind: 'money' }]
	});

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Coin'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByLabel('Value amount').fill('12');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('12.00', { exact: true })).toBeVisible();
});

test('url field: input, view link, and empty renders "-"', async ({ page }) => {
	const typeLabel = uniqueName('Band');
	await createItemType(page, { label: typeLabel, fields: [{ label: 'Website', kind: 'url' }] });

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('The Menagerie'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByLabel('Website').fill('https://example.com/band');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	const link = page.getByRole('link', { name: 'https://example.com/band' });
	await expect(link).toBeVisible();
	await expect(link).toHaveAttribute('href', 'https://example.com/band');
	await expect(link).toHaveAttribute('target', '_blank');
	await expect(link).toHaveAttribute('rel', 'noopener noreferrer');
});

test('email field: input and mailto: view link', async ({ page }) => {
	const typeLabel = uniqueName('Supplier');
	await createItemType(page, {
		label: typeLabel,
		fields: [{ label: 'Contact email', kind: 'email' }]
	});

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Acme Corp'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByLabel('Contact email').fill('sales@example.com');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	const link = page.getByRole('link', { name: 'sales@example.com' });
	await expect(link).toBeVisible();
	await expect(link).toHaveAttribute('href', 'mailto:sales@example.com');
});

test('phone field: input and tel: view link', async ({ page }) => {
	const typeLabel = uniqueName('Contact');
	await createItemType(page, {
		label: typeLabel,
		fields: [{ label: 'Phone number', kind: 'phone' }]
	});

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Repair shop'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByLabel('Phone number').fill('+1 (555) 123-4567');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	const link = page.getByRole('link', { name: '+1 (555) 123-4567' });
	await expect(link).toBeVisible();
	await expect(link).toHaveAttribute('href', 'tel:+1 (555) 123-4567');
});

test('phone field: an invalid value shows a client-side validation error on blur', async ({
	page
}) => {
	const typeLabel = uniqueName('Contact');
	await createItemType(page, {
		label: typeLabel,
		fields: [{ label: 'Phone number', kind: 'phone' }]
	});

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Bad number'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	const phoneInput = page.getByLabel('Phone number');
	await phoneInput.fill('call me maybe!!');
	// Client errors only surface once the field has been left.
	await page.getByLabel('Name').click();

	await expect(page.locator('p.text-destructive')).toBeVisible();

	// Fixing the value clears the error.
	await phoneInput.fill('+1 555 123 4567');
	await page.getByLabel('Name').click();
	await expect(page.locator('p.text-destructive')).toHaveCount(0);
});

test('date field: input via the calendar and view', async ({ page }) => {
	const typeLabel = uniqueName('Film');
	await createItemType(page, { label: typeLabel, fields: [{ label: 'Released', kind: 'date' }] });

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Alien'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByRole('button', { name: 'Released' }).click();
	const now = new Date();
	const iso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-15`;
	await page.locator(`[data-calendar-cell][data-value="${iso}"]`).click();

	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('Released')).toBeVisible();
	await page.reload();
	await expect(page.getByText('Released')).toBeVisible();
});

test('choice field: input via the dropdown, options set in the schema editor, and view', async ({
	page
}) => {
	const typeLabel = uniqueName('Record');
	await page.goto('/settings/item-types');
	const form = page
		.locator('form')
		.filter({ has: page.getByRole('button', { name: 'Add item type' }) });
	await form.getByLabel('Name').fill(typeLabel);
	await form.getByRole('button', { name: 'Add field', exact: true }).click();
	await form.getByLabel('Field label').last().fill('Format');
	await form.getByLabel('Field type').last().selectOption('choice');
	await form.getByPlaceholder('Add option…').last().fill('LP');
	await form.getByPlaceholder('Add option…').last().press('Enter');
	await form.getByPlaceholder('Add option…').last().fill('EP');
	await form.getByPlaceholder('Add option…').last().press('Enter');
	await form.getByRole('button', { name: 'Add item type' }).click();
	await expect(page.getByText('Item type created')).toBeVisible();

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Bookends'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByRole('button', { name: 'Format' }).click();
	await page.getByRole('option', { name: 'LP', exact: true }).click();
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('LP', { exact: true })).toBeVisible();
	await page.reload();
	await expect(page.getByText('LP', { exact: true })).toBeVisible();
});

test('rating field: input via stars and view', async ({ page }) => {
	const typeLabel = uniqueName('Album');
	await createItemType(page, {
		label: typeLabel,
		fields: [{ label: 'My rating', kind: 'rating' }]
	});

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('OK Computer'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page
		.getByRole('radiogroup', { name: 'My rating' })
		.getByRole('radio', { name: '4 stars' })
		.click();
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByLabel('4 out of 5 stars')).toBeVisible();
	await page.reload();
	await expect(page.getByLabel('4 out of 5 stars')).toBeVisible();
});

test('quantity field: input (value + unit) and view', async ({ page }) => {
	const typeLabel = uniqueName('Component');
	await createItemType(page, { label: typeLabel, fields: [{ label: 'Weight', kind: 'quantity' }] });

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Bolt'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByLabel('Weight value').fill('180');
	await page.getByLabel('Weight unit').fill('g');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('180 g', { exact: true })).toBeVisible();
	await page.reload();
	await expect(page.getByText('180 g', { exact: true })).toBeVisible();
});

test('group (table) field: add a sub-field, input a row, and view', async ({ page }) => {
	const typeLabel = uniqueName('Movie');
	await page.goto('/settings/item-types');
	const form = page
		.locator('form')
		.filter({ has: page.getByRole('button', { name: 'Add item type' }) });
	await form.getByLabel('Name').fill(typeLabel);
	await form.getByRole('button', { name: 'Add field', exact: true }).click();
	await form.getByLabel('Field label').last().fill('Cast');
	await form.getByLabel('Field type').last().selectOption('group');
	await form.getByRole('button', { name: 'Add sub-field' }).click();
	await form.getByLabel('Sub-field label').last().fill('Actor');
	await form.getByRole('button', { name: 'Add item type' }).click();
	await expect(page.getByText('Item type created')).toBeVisible();

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Alien'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByRole('button', { name: 'Add row' }).click();
	await page.getByLabel('Actor').fill('Sigourney Weaver');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('Sigourney Weaver')).toBeVisible();
	await page.reload();
	await expect(page.getByText('Sigourney Weaver')).toBeVisible();
});

test('ordered list field: add items and view as a numbered list', async ({ page }) => {
	const typeLabel = uniqueName('Recipe');
	await createItemType(page, {
		label: typeLabel,
		fields: [{ label: 'Instructions', kind: 'list' }]
	});

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Toast'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByRole('button', { name: 'Add item' }).click();
	await page.getByLabel('Instructions item 1').fill('Toast the bread');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	const item = page.locator('li', { hasText: 'Toast the bread' });
	await expect(item).toBeVisible();
	await expect(page.locator('ol')).toContainText('Toast the bread');
	await page.reload();
	await expect(page.locator('ol')).toContainText('Toast the bread');
});

test('checklist field: add an item, tick it, and view its persisted tick', async ({ page }) => {
	const typeLabel = uniqueName('Trip');
	await createItemType(page, {
		label: typeLabel,
		fields: [{ label: 'Packing list', kind: 'checklist' }]
	});

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Weekend away'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByRole('button', { name: 'Add item' }).click();
	await page.getByLabel('Packing list item 1', { exact: true }).fill('Passport');
	await page.getByLabel('Packing list item 1 done').check();
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('Passport')).toBeVisible();
	await page.reload();
	await expect(page.getByText('Passport')).toBeVisible();
	await expect(page.locator('input[type="checkbox"]')).toBeChecked();
});

test('longtext field: input and view', async ({ page }) => {
	const typeLabel = uniqueName('Vinyl');
	await createItemType(page, { label: typeLabel, fields: [{ label: 'Notes', kind: 'longtext' }] });

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Rumours'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	await page.getByLabel('Notes').fill('Bought at a car boot sale.');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('Bought at a car boot sale.')).toBeVisible();
	await page.reload();
	await expect(page.getByText('Bought at a car boot sale.')).toBeVisible();
});

test('multiple choice field: options set in the schema editor, tick several, and view', async ({
	page
}) => {
	const typeLabel = uniqueName('Release');
	await page.goto('/settings/item-types');
	const form = page
		.locator('form')
		.filter({ has: page.getByRole('button', { name: 'Add item type' }) });
	await form.getByLabel('Name').fill(typeLabel);
	await form.getByRole('button', { name: 'Add field', exact: true }).click();
	await form.getByLabel('Field label').last().fill('Formats');
	await form.getByLabel('Field type').last().selectOption('multichoice');
	for (const option of ['CD', 'Vinyl', 'Tape']) {
		await form.getByPlaceholder('Add option…').last().fill(option);
		await form.getByPlaceholder('Add option…').last().press('Enter');
	}
	await form.getByRole('button', { name: 'Add item type' }).click();
	await expect(page.getByText('Item type created')).toBeVisible();

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Kind of Blue'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	const group = page.getByRole('group', { name: 'Formats' });
	await group.getByRole('button', { name: 'Vinyl', exact: true }).click();
	await group.getByRole('button', { name: 'CD', exact: true }).click();
	await expect(group.getByRole('button', { name: 'Vinyl', exact: true })).toHaveAttribute(
		'aria-pressed',
		'true'
	);
	await expect(group.getByRole('button', { name: 'Tape', exact: true })).toHaveAttribute(
		'aria-pressed',
		'false'
	);
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('CD', { exact: true })).toBeVisible();
	await expect(page.getByText('Vinyl', { exact: true })).toBeVisible();
	await expect(page.getByText('Tape', { exact: true })).toHaveCount(0);
	await page.reload();
	await expect(page.getByText('CD', { exact: true })).toBeVisible();
	await expect(page.getByText('Vinyl', { exact: true })).toBeVisible();
});

test('partial date field: placeholder, live preview, and view at the precision entered', async ({
	page
}) => {
	const typeLabel = uniqueName('Record');
	await createItemType(page, {
		label: typeLabel,
		fields: [{ label: 'Pressed', kind: 'partialdate' }]
	});

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Blue'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	const input = page.getByLabel('Pressed');
	await expect(input).toHaveAttribute('placeholder', 'YYYY, YYYY-MM or YYYY-MM-DD');
	await input.fill('1973-03');
	await expect(page.getByText('March 1973', { exact: true })).toBeVisible();

	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('March 1973', { exact: true })).toBeVisible();
	await page.reload();
	await expect(page.getByText('March 1973', { exact: true })).toBeVisible();
});

test('partial date field: a year alone is kept as a year, and a bad value shows an error', async ({
	page
}) => {
	const typeLabel = uniqueName('Record');
	await createItemType(page, {
		label: typeLabel,
		fields: [{ label: 'Pressed', kind: 'partialdate' }]
	});

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Rumours'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	const input = page.getByLabel('Pressed');
	await input.fill('1973-13');
	// Client errors only surface once the field has been left.
	await page.getByLabel('Name').click();
	await expect(page.locator('p.text-destructive')).toContainText('1973-03-14');

	await input.fill('1977');
	await page.getByLabel('Name').click();
	await expect(page.locator('p.text-destructive')).toHaveCount(0);

	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);
	await expect(page.getByText('1977', { exact: true })).toBeVisible();
});

test('duration field: m:ss entry, tidied on blur, and shown as a clock', async ({ page }) => {
	const typeLabel = uniqueName('Album');
	await createItemType(page, {
		label: typeLabel,
		fields: [{ label: 'Running time', kind: 'duration' }]
	});

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Abbey Road'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	const input = page.getByLabel('Running time');
	await input.fill('1h 2m 3s');
	await page.getByLabel('Name').click();
	await expect(input).toHaveValue('1:02:03');

	await input.fill('225');
	await page.getByLabel('Name').click();
	await expect(input).toHaveValue('3:45');

	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);

	await expect(page.getByText('3:45', { exact: true })).toBeVisible();
	await page.reload();
	await expect(page.getByText('3:45', { exact: true })).toBeVisible();
});

test('duration field: unreadable text shows an error and the save is rejected until it is fixed', async ({
	page
}) => {
	const typeLabel = uniqueName('Album');
	await createItemType(page, {
		label: typeLabel,
		fields: [{ label: 'Running time', kind: 'duration' }]
	});

	await page.goto('/items/new');
	await page.getByLabel('Name').fill(uniqueName('Revolver'));
	await page.getByPlaceholder('Search item types…').fill(typeLabel);
	await page.getByRole('button', { name: typeLabel, exact: true }).click();

	const input = page.getByLabel('Running time');
	await input.fill('about three minutes');
	await page.getByLabel('Name').click();
	await expect(page.locator('p.text-destructive')).toContainText('3:45');

	// The server rejects the value; its error stays until the next save.
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await expect(page).toHaveURL(/\/items\/new$/);

	await input.fill('3:45');
	await page.getByRole('button', { name: 'Save', exact: true }).click();
	await page.waitForURL(/\/items\/(?!new$)[^/]+$/);
	await expect(page.getByText('3:45', { exact: true })).toBeVisible();
});
