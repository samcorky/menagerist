import { test, expect, type Locator, type Page } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * Phone-only layout checks, run by the `mobile` project at two widths: the bottom bar, page
 * overflow, dialog fit and tap targets. Measured sizes are attached as annotations so the owner
 * can see them in the report.
 */
test.describe.configure({ mode: 'serial' });

const SIZES = [
	{ width: 360, height: 740 },
	{ width: 320, height: 640 }
];
const GUIDELINE_TARGET = 44;

const { makeCollection, makeItem, addToCollection, cleanUp } = ownedData();
let installedPacks: string[] = [];

test.afterEach(async ({ request }) => {
	await cleanUp(request);
	for (const id of installedPacks) await request.delete(`/api/v1/example/${id}/installation`);
	installedPacks = [];
});

type Box = { x: number; y: number; width: number; height: number };

async function box(locator: Locator): Promise<Box> {
	await expect(locator).toBeVisible();
	const b = await locator.boundingBox();
	expect(b, 'element has a bounding box').not.toBeNull();
	return b!;
}

function inside(b: Box, vw: number, vh: number): boolean {
	return b.x >= -0.5 && b.y >= -0.5 && b.x + b.width <= vw + 0.5 && b.y + b.height <= vh + 0.5;
}

/** Whether a box sits inside the layout viewport the page actually has (see `overflow`). */
async function fits(page: Page, b: Box): Promise<boolean> {
	const vp = await page.evaluate(() => ({ w: window.innerWidth, h: window.innerHeight }));
	return inside(b, vp.w, vp.h);
}

/**
 * Side of the largest square around the element's centre that a finger would still hit the
 * element in. The visible box can be smaller than this when an ::after pseudo-element extends it.
 */
async function hitArea(locator: Locator): Promise<number> {
	return locator.evaluate((el) => {
		const r = el.getBoundingClientRect();
		const cx = r.x + r.width / 2;
		const cy = r.y + r.height / 2;
		let best = 0;
		for (let half = 4; half <= 40; half += 1) {
			// Probe just inside the edge: a box's far edge is not part of it.
			const d = half - 0.5;
			const corners = [
				[cx - d, cy - d],
				[cx + d, cy - d],
				[cx - d, cy + d],
				[cx + d, cy + d]
			];
			const hit = corners.every(([x, y]) => {
				const t = document.elementFromPoint(x, y);
				return !!t && el.contains(t);
			});
			if (!hit) break;
			best = half * 2;
		}
		return best;
	});
}

function round(n: number) {
	return Math.round(n * 10) / 10;
}

/**
 * Waits for the page's data to settle, then reports how far content spills past the viewport.
 * A mobile browser zooms out to fit wide content, so `innerWidth` growing past the configured
 * width is itself the overflow signal; the widest offenders are listed to help find the cause.
 */
async function overflow(page: Page, width: number) {
	await page.waitForLoadState('networkidle');
	return page.evaluate((target) => {
		const main = document.getElementById('main-scroll');
		const wide = [...document.body.querySelectorAll<HTMLElement>('*')]
			.map((el) => ({ el, right: el.getBoundingClientRect().right }))
			.filter(({ right }) => right > target + 0.5)
			.sort((a, b) => b.right - a.right)
			.slice(0, 4)
			.map(
				({ el, right }) =>
					`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 50)} right=${Math.round(right)}`
			);
		return {
			innerWidth: window.innerWidth,
			innerHeight: window.innerHeight,
			documentScrollWidth: document.documentElement.scrollWidth,
			mainScrollWidth: main?.scrollWidth ?? 0,
			mainClientWidth: main?.clientWidth ?? 0,
			wide
		};
	}, width);
}

async function seed(request: Parameters<typeof makeCollection>[0]) {
	const collection = await makeCollection(
		request,
		uniqueName('Phone collection of rather long name')
	);
	const item = await makeItem(
		request,
		uniqueName('Phone item with a rather long descriptive name')
	);
	await addToCollection(request, collection.id, [item.id]);
	return { collection, item };
}

for (const size of SIZES) {
	test.describe(`${size.width}x${size.height}`, () => {
		test.beforeEach(async ({ page }) => {
			await page.setViewportSize(size);
		});

		test('no page scrolls horizontally', async ({ page, request }) => {
			const { collection, item } = await seed(request);
			const routes = [
				'/',
				'/items',
				'/collections',
				`/items/${item.id}`,
				`/collections/${collection.id}`,
				'/settings/examples'
			];
			const offenders: string[] = [];
			for (const route of routes) {
				await page.goto(route);
				const m = await overflow(page, size.width);
				test.info().annotations.push({
					type: `overflow ${size.width} ${route}`,
					description: JSON.stringify(m)
				});
				if (
					m.innerWidth > size.width ||
					m.documentScrollWidth > size.width ||
					m.mainScrollWidth > m.mainClientWidth
				) {
					offenders.push(`${route}: ${JSON.stringify(m)}`);
				}
			}
			expect(offenders, 'pages wider than the viewport').toEqual([]);
		});

		test('bottom navigation fits and is tappable', async ({ page }) => {
			await page.goto('/');
			const nav = page.locator('nav:visible').last();
			const labels = ['Home', 'Items', 'Collections', 'Search', 'New', 'Settings'];
			const entries = nav.locator('a, button');
			await expect(entries).toHaveCount(labels.length);

			const measured: { label: string; b: Box; truncated: boolean }[] = [];
			for (let i = 0; i < labels.length; i++) {
				const entry = entries.nth(i);
				const label = entry.locator('span');
				const truncated = await label.evaluate((el) => el.scrollWidth > el.clientWidth);
				measured.push({ label: (await label.innerText()).trim(), b: await box(entry), truncated });
			}
			expect(measured.map((m) => m.label)).toEqual(labels);

			for (const m of measured) {
				test.info().annotations.push({
					type: `nav ${size.width} ${m.label}`,
					description: `${round(m.b.width)}x${round(m.b.height)} at x=${round(m.b.x)}`
				});
				expect(inside(m.b, size.width, size.height), `${m.label} inside viewport`).toBe(true);
				expect(m.truncated, `${m.label} label truncated`).toBe(false);
			}
			for (let i = 0; i < measured.length; i++) {
				for (let j = i + 1; j < measured.length; j++) {
					const a = measured[i].b;
					const c = measured[j].b;
					const overlap = a.x < c.x + c.width && c.x < a.x + a.width;
					expect(overlap, `${measured[i].label} overlaps ${measured[j].label}`).toBe(false);
				}
			}

			const minW = Math.min(...measured.map((m) => m.b.width));
			const minH = Math.min(...measured.map((m) => m.b.height));
			test.info().annotations.push({
				type: `nav ${size.width} smallest target`,
				description: `${round(minW)}x${round(minH)} (guideline ${GUIDELINE_TARGET})`
			});
			expect(minW).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
			expect(minH).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
		});

		test('dialogs fit the viewport and return focus', async ({ page, request }) => {
			const { collection, item } = await seed(request);

			async function checkDialog(trigger: Locator, name: string, primary: string | RegExp) {
				await trigger.tap();
				const dialog = page.getByRole('dialog', { name });
				const d = await box(dialog);
				test.info().annotations.push({
					type: `dialog ${size.width} ${name}`,
					description: `${round(d.x)},${round(d.y)} ${round(d.width)}x${round(d.height)}`
				});
				const vp = await page.evaluate(() => `${innerWidth}x${innerHeight}`);
				expect
					.soft(await fits(page, d), `${name} inside viewport ${vp}: ${JSON.stringify(d)}`)
					.toBe(true);
				const spill = await dialog.evaluate((el) => el.scrollWidth - el.clientWidth);
				expect(spill, `${name} horizontal overflow`).toBeLessThanOrEqual(0);
				const button = dialog.getByRole('button', { name: primary }).last();
				await button.scrollIntoViewIfNeeded();
				expect(await fits(page, await box(button)), `${name} primary button`).toBe(true);
				await page.keyboard.press('Escape');
				await expect(dialog).toBeHidden();
				await expect(trigger).toBeFocused();
			}

			await page.goto('/collections');
			await checkDialog(
				page.getByRole('button', { name: 'New collection' }).first(),
				'New collection',
				/^Create/
			);

			await page.goto(`/collections/${collection.id}`);
			await checkDialog(
				page.getByRole('button', { name: 'Add items' }).first(),
				'Add items',
				/^Add /
			);

			await page.goto(`/items/${item.id}`);
			await checkDialog(
				page.getByRole('button', { name: 'Add to collection' }),
				'Add to collection',
				'Close'
			);
		});

		test('the search popup opens from the bottom bar and fits the viewport', async ({
			page,
			request
		}) => {
			const item = await makeItem(request, uniqueName('Phone search item'));
			await page.goto('/');
			const button = page.getByRole('button', { name: 'Search items' });
			const b = await box(button);
			test.info().annotations.push({
				type: `search button ${size.width}`,
				description: `${round(b.width)}x${round(b.height)}`
			});
			expect(b.width).toBeGreaterThanOrEqual(44);
			expect(b.height).toBeGreaterThanOrEqual(44);

			await button.tap();
			const dialog = page.getByRole('dialog', { name: 'Search items' });
			const d = await box(dialog);
			test.info().annotations.push({
				type: `search popup ${size.width}`,
				description: `${round(d.x)},${round(d.y)} ${round(d.width)}x${round(d.height)}`
			});
			expect(await fits(page, d), 'popup inside viewport').toBe(true);
			const spill = await dialog.evaluate((el) => el.scrollWidth - el.clientWidth);
			expect(spill, 'popup horizontal overflow').toBeLessThanOrEqual(0);

			await page.keyboard.press('Escape');
			await expect(dialog).toBeHidden();
			await expect(button).toBeFocused();

			await button.tap();
			await dialog.getByPlaceholder('Search your items…').fill(item.name);
			const row = dialog.getByRole('option', { name: new RegExp(item.name) });
			await expect(row).toBeVisible();
			expect(await fits(page, await box(row)), 'first result inside viewport').toBe(true);
			await row.tap();
			await expect(page).toHaveURL(new RegExp(`/items/${item.id}$`));
		});

		test('remove-from-collection is a reachable touch target', async ({ page, request }) => {
			const { collection, item } = await seed(request);
			await page.goto(`/collections/${collection.id}`);
			const remove = page.getByRole('button', {
				name: `Remove ${item.name} from this collection`
			});
			// Centre it so the bottom bar can't cover part of its hit area.
			await remove.evaluate((el) => el.scrollIntoView({ block: 'center' }));
			const b = await box(remove);
			const reach = await hitArea(remove);
			test.info().annotations.push({
				type: `remove target ${size.width}`,
				description: `box ${round(b.width)}x${round(b.height)}, hit area about ${reach}x${reach}`
			});
			expect(Math.max(b.width, reach)).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
			expect(Math.max(b.height, reach)).toBeGreaterThanOrEqual(GUIDELINE_TARGET);

			await remove.tap();
			await expect(page.getByText('Nothing in this collection yet.')).toBeVisible();
		});

		test('item page remove-from-collection is a 44px touch target', async ({ page, request }) => {
			const { collection, item } = await seed(request);
			await page.goto(`/items/${item.id}`);
			const remove = page.getByRole('button', { name: `Remove from ${collection.name}` });
			await remove.evaluate((el) => el.scrollIntoView({ block: 'center' }));
			const b = await box(remove);
			const reach = await hitArea(remove);
			test.info().annotations.push({
				type: `item remove target ${size.width}`,
				description: `box ${round(b.width)}x${round(b.height)}, hit area about ${reach}x${reach}`
			});
			expect(Math.max(b.width, reach)).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
			expect(Math.max(b.height, reach)).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
		});

		test('Examples controls are visible and tappable', async ({ page }) => {
			await page.goto('/settings/examples');
			const add = page.getByRole('button', { name: /^Add Music/ });
			await add.scrollIntoViewIfNeeded();
			const a = await box(add);
			test.info().annotations.push({
				type: `examples add button ${size.width}`,
				description: `${round(a.width)}x${round(a.height)}`
			});
			expect(await fits(page, a)).toBe(true);
			expect(a.height).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
			installedPacks.push('music');
			await add.tap();
			const remove = page.getByRole('button', { name: /^Remove Music/ });
			await expect(remove).toBeVisible();
			await remove.scrollIntoViewIfNeeded();
			const r = await box(remove);
			expect(await fits(page, r)).toBe(true);
			expect(r.height).toBeGreaterThanOrEqual(GUIDELINE_TARGET);

			await page.goto('/items');
			const select = page.getByLabel('Examples');
			await select.scrollIntoViewIfNeeded();
			const s = await box(select);
			test.info().annotations.push({
				type: `examples select ${size.width}`,
				description: `${round(s.width)}x${round(s.height)} at x=${round(s.x)}`
			});
			expect(await fits(page, s)).toBe(true);
			expect(s.height).toBeGreaterThanOrEqual(GUIDELINE_TARGET);
			await select.tap();
			await select.selectOption({ index: 1 });
		});
	});
}
