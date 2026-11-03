import { expect, test, type Page } from './fixtures';

/**
 * The app shell must fit the visible area, with #main-scroll the only thing that scrolls. On
 * Chrome for Android `100dvh` can be taller than what is visible (collapsing browser bars, the
 * gesture area), which made the whole document scroll: the sticky header stayed put while the
 * bottom navigation rode up and left a blank band under it.
 *
 * Playwright's `dvh` always equals the visible height, so the specs force the shell taller than
 * the viewport, as the browser does, and check that the document still cannot move.
 */

const ROUTES = ['/status', '/items'];

/** The shell is the element wrapping the header, the sidebar/page row and the bottom navigation. */
async function growShellBeyondViewport(page: Page, extra: number) {
	await page.evaluate((px) => {
		const shell = document.getElementById('main-scroll')?.parentElement?.parentElement;
		if (!shell) throw new Error('app shell not found');
		shell.style.height = `calc(100dvh + ${px}px)`;
	}, extra);
}

for (const route of ROUTES) {
	test(`${route}: the document never scrolls, even when the shell outgrows the viewport`, async ({
		page
	}) => {
		await page.goto(route);
		await expect(page.locator('#main-scroll main').first()).toBeVisible();
		await growShellBeyondViewport(page, 200);

		await page.evaluate(() => window.scrollTo(0, 1000));
		const document_ = await page.evaluate(() => ({
			scrollY: window.scrollY,
			scrollHeight: document.scrollingElement?.scrollHeight ?? 0,
			innerHeight: window.innerHeight
		}));
		expect(document_.scrollY, 'document scroll position').toBe(0);
		expect(document_.scrollHeight, 'document scroll height').toBeLessThanOrEqual(
			document_.innerHeight
		);
	});

	test(`${route}: the bottom navigation stays pinned to the bottom while the page scrolls`, async ({
		page
	}) => {
		await page.goto(route);
		await expect(page.locator('#main-scroll main').first()).toBeVisible();

		await page.evaluate(() => {
			const main = document.getElementById('main-scroll');
			if (main) main.scrollTop = main.scrollHeight;
		});

		// The bottom bar has no accessible name of its own; its view-transition name identifies it.
		const nav = page.locator('nav[style*="site-nav"]');
		const box = await nav.boundingBox();
		const innerHeight = await page.evaluate(() => window.innerHeight);
		expect(box, 'bottom navigation is rendered').not.toBeNull();
		expect(box!.y + box!.height, 'bottom navigation reaches the bottom edge').toBeCloseTo(
			innerHeight,
			0
		);
	});
}
