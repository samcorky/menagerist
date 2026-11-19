import { readFileSync } from 'node:fs';
import { test, expect, type Page, type Route } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * On the item page the cover keeps its place and size from the loading state to the full-size
 * picture: the thumbnail and then the full picture only make it sharper (#632).
 */
const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

const photos = {
	landscape: 'cover-landscape.jpg',
	portrait: 'cover-portrait.jpg',
	// Stored 2400x1350 with EXIF orientation 6, so it shows as a portrait.
	rotated: 'cover-rotated.jpg'
} as const;

const viewports = {
	desktop: { width: 1440, height: 900 },
	phone: { width: 390, height: 844 }
};

type Box = { x: number; y: number; width: number; height: number };

/** Holds every request to `pattern` until `release()` is called. */
async function hold(page: Page, pattern: RegExp) {
	let release = () => {};
	const released = new Promise<void>((resolve) => (release = resolve));
	await page.route(pattern, async (route: Route) => {
		await released;
		await route.continue();
	});
	return release;
}

/** Records the cover's box every animation frame from the first one it exists in. */
async function recordCoverBoxes(page: Page) {
	await page.addInitScript(() => {
		const boxes: Box[] = [];
		(window as unknown as { __coverBoxes: Box[] }).__coverBoxes = boxes;
		const tick = () => {
			// Only once its pictures are in the page, when the cover's shape is known.
			const cover = document.querySelector('[data-testid="item-cover"]');
			if (cover?.querySelector('img')) {
				const r = cover.getBoundingClientRect();
				boxes.push({ x: r.x, y: r.y, width: r.width, height: r.height });
			}
			requestAnimationFrame(tick);
		};
		requestAnimationFrame(tick);
	});
	return () => page.evaluate(() => (window as unknown as { __coverBoxes: Box[] }).__coverBoxes);
}

function expectSameBox(actual: Box, expected: Box, what: string) {
	for (const key of ['x', 'y', 'width', 'height'] as const) {
		expect(Math.abs(actual[key] - expected[key]), `${what}: ${key}`).toBeLessThanOrEqual(1);
	}
}

for (const [viewportName, viewport] of Object.entries(viewports)) {
	for (const [shape, file] of Object.entries(photos)) {
		test(`on a ${viewportName}, the ${shape} cover keeps its box from loading to the full picture`, async ({
			page,
			request
		}) => {
			await page.setViewportSize(viewport);
			const item = await makeItem(request, uniqueName(`Cover ${shape}`));
			const uploaded = await request.post('/api/v1/media/attachments', {
				multipart: {
					file: {
						name: file,
						mimeType: 'image/jpeg',
						buffer: readFileSync(new URL(`./assets/${file}`, import.meta.url))
					},
					target_type: 'node',
					target_id: item.id,
					attribute_key: 'cover'
				}
			});
			expect(uploaded.ok()).toBe(true);

			const releaseThumb = await hold(page, /\/api\/v1\/media\/[^/]+\/thumbnail$/);
			const releaseFull = await hold(page, /\/api\/v1\/media\/[^/]+\/content$/);
			const coverBoxes = await recordCoverBoxes(page);

			await page.goto(`/items/${item.id}`);
			const cover = page.getByTestId('item-cover');
			const [thumb, full] = [cover.locator('img').nth(0), cover.locator('img').nth(1)];

			// Neither picture has arrived: the loading state holds the space.
			await expect(cover.getByTestId('cover-loading')).toBeVisible();
			await expect(full).toBeAttached();
			const waiting = (await cover.boundingBox())!;

			releaseThumb();
			await expect(thumb).toHaveCSS('opacity', '1');
			await expect(full).toHaveCSS('opacity', '0');
			expectSameBox((await cover.boundingBox())!, waiting, 'thumbnail');

			releaseFull();
			await expect(full).toHaveCSS('opacity', '1');
			expectSameBox((await cover.boundingBox())!, waiting, 'full picture');

			// No frame in between, such as the moment either picture is decoded, moved it.
			for (const box of await coverBoxes()) expectSameBox(box, waiting, 'a frame');
		});
	}
}
