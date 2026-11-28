import { test, expect } from './fixtures';
import { ownedData, uniqueName } from './helpers';

/**
 * The next page of an infinite list starts loading well before its foot is on screen (#588).
 *
 * Pages scroll inside `#main-scroll`. An observer rooted at the viewport ignores its margin for
 * a target inside a scrolling container, so the foot has to observe from that container.
 */
const { makeItem, cleanUp } = ownedData();

test.afterEach(({ request }) => cleanUp(request));

test('the list foot watches from the scrolling container, so the margin counts', async ({
	page,
	request
}) => {
	await makeItem(request, uniqueName('Load ahead'));
	await page.addInitScript(() => {
		const seen: { root: string | null; margin: string }[] = [];
		(window as unknown as { __observers: typeof seen }).__observers = seen;
		const Original = window.IntersectionObserver;
		window.IntersectionObserver = class extends Original {
			constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
				super(callback, options);
				const root = options?.root instanceof Element ? options.root.id : null;
				seen.push({ root, margin: options?.rootMargin ?? '' });
			}
		};
	});
	// Say there is a next page, so the foot shows its sentinel whatever else the library holds.
	await page.route(/\/api\/v1\/nodes\?(?!.*after=)/, async (route) => {
		const response = await route.fetch();
		await route.fulfill({
			response,
			headers: { ...response.headers(), link: '</api/v1/nodes?after=next&limit=50>; rel="next"' }
		});
	});
	await page.setViewportSize({ width: 1280, height: 800 });
	await page.goto('/items');

	// The fake next page fails and takes the sentinel with it, so read what was observed.
	await expect
		.poll(() =>
			page.evaluate(() =>
				(
					window as unknown as { __observers: { root: string | null; margin: string }[] }
				).__observers.some((o) => o.root === 'main-scroll' && o.margin === '2000px')
			)
		)
		.toBe(true);
});
