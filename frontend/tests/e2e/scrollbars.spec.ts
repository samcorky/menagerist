import { test, expect, type Page } from './fixtures';

/** Scrollbars are thin and take the theme's colour, except where a list hides them on purpose. */
const sidebarList = (page: Page) =>
	page.getByRole('navigation', { name: 'Main', exact: true }).locator('.overflow-y-auto').first();

const scrollbar = (page: Page, el: ReturnType<typeof sidebarList>) =>
	el.evaluate((node) => {
		const style = getComputedStyle(node);
		return { width: style.scrollbarWidth, colour: style.scrollbarColor };
	});

/** The thumb colour the page's theme defines, resolved the way the browser reports it. */
const themeThumb = (page: Page) =>
	page.evaluate(() => {
		const probe = document.createElement('div');
		probe.style.color = 'var(--scrollbar-thumb)';
		document.body.append(probe);
		const colour = getComputedStyle(probe).color;
		probe.remove();
		return colour;
	});

for (const scheme of ['light', 'dark'] as const) {
	test(`in the ${scheme} theme, the sidebar's scrollbar is thin and themed`, async ({ page }) => {
		await page.emulateMedia({ colorScheme: scheme });
		await page.setViewportSize({ width: 1280, height: 320 });
		await page.goto('/items');
		const list = sidebarList(page);
		await expect(list).toBeVisible();

		const thumb = await themeThumb(page);
		expect(await scrollbar(page, list)).toEqual({
			width: 'thin',
			colour: `${thumb} rgba(0, 0, 0, 0)`
		});
	});
}

// The attachment strip and the command list hide their bars with these utilities.
for (const utility of ['scrollbar-none', 'no-scrollbar']) {
	test(`the ${utility} utility still hides the scrollbar`, async ({ page }) => {
		await page.goto('/items');
		await expect(page.getByRole('navigation', { name: 'Main', exact: true })).toBeVisible();
		const width = await page.evaluate((cls) => {
			const probe = document.createElement('div');
			probe.className = cls;
			document.body.append(probe);
			const value = getComputedStyle(probe).scrollbarWidth;
			probe.remove();
			return value;
		}, utility);
		expect(width).toBe('none');
	});
}
