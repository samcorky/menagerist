import { test as base } from '@playwright/test';

export * from '@playwright/test';

/** Backend port of worker 0; worker i listens on this + i (see playwright.config.ts). */
export const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8100);

/**
 * Each worker has its own backend (serving the built SPA) and database, so `baseURL` follows
 * `parallelIndex`. Overriding the built-in fixture makes `page` and `request` both pick it up.
 */
export const test = base.extend({
	// eslint-disable-next-line no-empty-pattern -- Playwright parses the first argument
	baseURL: async ({}, use, testInfo) => {
		await use(`http://localhost:${BACKEND_PORT + testInfo.parallelIndex}`);
	}
});
