import { test, expect, type Page } from './fixtures';

/**
 * Scrollbars are thin and take the theme's colour, except where a list hides them on purpose.
 * Chromium would draw arrow buttons on a standard thin bar, so there the bar is drawn with the
 * ::-webkit-scrollbar pseudo-elements instead (the standard properties go back to auto).
 */
const sidebarList = (page: Page) =>
	page.getByRole('navigation', { name: 'Main', exact: true }).locator('.overflow-y-auto').first();

const scrollbar = (page: Page, el: ReturnType<typeof sidebarList>) =>
	el.evaluate((node) => {
		const style = getComputedStyle(node);
		const thumb = getComputedStyle(node, '::-webkit-scrollbar-thumb');
		return {
			standardWidth: style.scrollbarWidth,
			barWidth: getComputedStyle(node, '::-webkit-scrollbar').width,
			buttons: getComputedStyle(node, '::-webkit-scrollbar-button').display,
			thumbColour: thumb.backgroundColor,
			thumbRadius: thumb.borderTopLeftRadius
		};
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
			standardWidth: 'auto',
			barWidth: '10px',
			buttons: 'none',
			thumbColour: thumb,
			thumbRadius: expect.stringMatching(/^[1-9]/)
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
