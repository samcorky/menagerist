import { readFileSync } from 'node:fs';
import { test, expect, type APIRequestContext } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/** Changing the cover from the Files gallery changes the cover shown above it (#762). */
const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const picture = (name: string) => readFileSync(new URL(`./assets/${name}`, import.meta.url));

async function attach(
	request: APIRequestContext,
	itemId: string,
	file: { name: string; asset: string },
	cover: boolean
): Promise<void> {
	const res = await request.post('/api/v1/media/attachments', {
		multipart: {
			file: { name: file.name, mimeType: 'image/jpeg', buffer: picture(file.asset) },
			target_type: 'node',
			target_id: itemId,
			...(cover ? { attribute_key: 'cover' } : {})
		}
	});
	expect(res.status(), await res.text()).toBeLessThan(300);
}

test('a cover set from the gallery replaces the one shown above it', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Two pictures'));
	await attach(request, item.id, { name: 'front.jpg', asset: 'cover-landscape.jpg' }, true);
	await attach(request, item.id, { name: 'back.jpg', asset: 'cover-portrait.jpg' }, false);
	await page.goto(`/items/${item.id}`);

	// The gallery has read the item's media, so the cover above has too.
	await expect(page.getByRole('button', { name: 'Remove cover for front.jpg' })).toBeVisible();
	// The cover's picture is the one the gallery's front.jpg points at; its address says which.
	const shown = page.getByTestId('item-cover').locator('img').first();
	await expect(shown).toHaveAttribute('src', /\/api\/v1\/media\/[^/]+\//);
	const before = await shown.getAttribute('src');

	await page.getByRole('button', { name: 'Set as cover back.jpg' }).click();
	await expect(page.getByRole('button', { name: 'Remove cover for back.jpg' })).toBeVisible();

	// Without a reload, the picture above is the other one.
	await expect(page.getByTestId('item-cover').locator('img').first()).not.toHaveAttribute(
		'src',
		before ?? ''
	);
});

test('removing the cover in the gallery brings back the placeholder', async ({ page, request }) => {
	const item = await makeItem(request, uniqueName('Loses its cover'));
	await attach(request, item.id, { name: 'front.jpg', asset: 'cover-landscape.jpg' }, true);
	await page.goto(`/items/${item.id}`);
	await expect(page.getByTestId('item-cover').locator('img').first()).toBeVisible();

	await page.getByRole('button', { name: 'Remove cover for front.jpg' }).click();

	await expect(page.getByTestId('cover-placeholder')).toBeVisible();
});
